from functools import lru_cache
from build_patch import generate


@lru_cache(maxsize=1)
def built_patch():return generate()
