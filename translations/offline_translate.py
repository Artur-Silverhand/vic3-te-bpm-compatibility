"""Local Argos/CT2 draft generation; no text is sent to an external service."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import time

from loclib import ROOT,digest,json_write,marker_ids,translatable


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--cuda-bin',default='C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8/bin')
    args=parser.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    dependencies=ROOT/'runtime/translation-pydeps';sys.path.insert(0,str(dependencies))
    handle=None
    if args.device=='cuda':
        folder=Path(args.cuda_bin)
        if not folder.is_dir():raise ValueError('CUDA bin directory unavailable; specify --cuda-bin or use --device cpu')
        os.environ['PATH']=str(folder)+os.pathsep+os.environ.get('PATH','')
        handle=os.add_dll_directory(str(folder))
    import ctranslate2
    import sentencepiece as spm
    model=ROOT/'runtime/translation-model/translate-en_ru-1_9'
    tokenizer=spm.SentencePieceProcessor(model_file=str(model/'sentencepiece.model'))
    engine=ctranslate2.Translator(str(model/'model'),device=args.device,
        compute_type='float16' if args.device=='cuda' else 'int8',inter_threads=1,intra_threads=4)
    work=ROOT/'runtime/translations'
    templates=json.loads((work/'te-templates.json').read_text(encoding='utf-8'))
    snippets=json.loads((work/'concept-labels.json').read_text(encoding='utf-8'))
    jobs={key:value['en'] for key,value in templates.items()}
    for source,identifier in snippets.items():jobs.setdefault(identifier,source)
    cache_path=work/'offline-cache.jsonl';cache={}
    if cache_path.exists():
        for line in cache_path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                try:row=json.loads(line)
                except json.JSONDecodeError:continue
                cache[row['id']]=row
    pending=[(key,text) for key,text in jobs.items() if key not in cache]
    pending.sort(key=lambda item:len(item[1]))
    if args.limit:pending=pending[:args.limit]
    start=time.monotonic();done=0;failures=0;generated_tokens=0
    with cache_path.open('a',encoding='utf-8',newline='\n') as output:
        for start_index in range(0,len(pending),64):
            batch=pending[start_index:start_index+64]
            encoded=[tokenizer.encode(text,out_type=str) for _,text in batch]
            maximum=max(map(len,encoded),default=1)
            results=engine.translate_batch(encoded,beam_size=3,max_batch_size=1536,batch_type='tokens',
                max_input_length=0,max_decoding_length=max(256,maximum*3+64),no_repeat_ngram_size=6)
            for (identifier,en),tokens,result in zip(batch,encoded,results):
                ru=tokenizer.decode(result.hypotheses[0])
                # Repair spelling of our own sentinel only, never an actual game identifier.
                ru=re.sub(r'_+\s*PH\s*_?\s*(\d+)\s*_+',lambda m:'__PH'+m[1]+'__',ru,flags=re.I)
                valid=marker_ids(en)==marker_ids(ru)
                status='draft' if valid else 'placeholder_retry_required'
                if len(result.hypotheses[0])>=max(256,maximum*3+64)-1:status='truncation_retry_required'
                row={'id':identifier,'en':en,'ru':ru,'status':status,'engine':'argos-en-ru-1.9-ct2'}
                output.write(json.dumps(row,ensure_ascii=False)+'\n');cache[identifier]=row
                done+=1;generated_tokens+=len(result.hypotheses[0]);failures+=status!='draft'
            output.flush()
            state={'phase':'first_pass','total_jobs':len(jobs),'cached':len(cache),'done_this_run':done,
                   'pending_this_run':len(pending)-done,'structural_retries':failures,
                   'seconds':round(time.monotonic()-start,1),'generated_tokens':generated_tokens,'device':args.device}
            json_write(work/'offline-progress.json',state)
            print(json.dumps(state),flush=True)
    # Sentinel failures are retried as protected literal + translated text segments.
    failed=[row for key,row in cache.items() if key in jobs and row['status'] not in {'draft','segmented_draft'}]
    pieces={}
    for row in failed:
        for part in re.split(r'(__PH\d+__)',row['en']):
            if part and not re.fullmatch(r'__PH\d+__',part) and re.search(r'[A-Za-z]{2}',part):
                pieces[digest('piece:'+part.strip())]=part.strip()
    translated_pieces={}
    for start_index in range(0,len(pieces),64):
        batch=list(pieces.items())[start_index:start_index+64]
        encoded=[tokenizer.encode(value,out_type=str) for _,value in batch]
        maximum=max(map(len,encoded),default=1)
        results=engine.translate_batch(encoded,beam_size=3,max_batch_size=1536,batch_type='tokens',
            max_input_length=0,max_decoding_length=max(256,maximum*3+64),no_repeat_ngram_size=6)
        for (key,en),result in zip(batch,results):translated_pieces[key]=tokenizer.decode(result.hypotheses[0])
        json_write(work/'offline-progress.json',{'phase':'repair','pieces_total':len(pieces),
                  'pieces_done':len(translated_pieces),'seconds':round(time.monotonic()-start,1)})
    with cache_path.open('a',encoding='utf-8',newline='\n') as output:
        for row in failed:
            assembled=[]
            for part in re.split(r'(__PH\d+__)',row['en']):
                if not part:continue
                if re.fullmatch(r'__PH\d+__',part) or not re.search(r'[A-Za-z]{2}',part):assembled.append(part);continue
                leading=part[:len(part)-len(part.lstrip())];trailing=part[len(part.rstrip()):]
                assembled.append(leading+translated_pieces[digest('piece:'+part.strip())]+trailing)
            repaired=''.join(assembled)
            assert marker_ids(row['en'])==marker_ids(repaired)
            item={**row,'ru':repaired,'status':'segmented_draft'};output.write(json.dumps(item,ensure_ascii=False)+'\n')
            cache[row['id']]=item
    summary={'phase':'complete','total_jobs':len(jobs),'cached':len(cache),
             'remaining':len(set(jobs)-set(cache)),'segmented_drafts':len(failed),
             'seconds':round(time.monotonic()-start,1),'engine':'argos-en-ru-1.9-ct2','device':args.device}
    json_write(work/'offline-progress.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
