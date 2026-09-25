from .global_apis import Arbeitnow, HackerNewsHiring, Himalayas, RemoteOK, Remotive
from .taiwan import Cake, Job104, TaiwanJobs, Yourator

ALL_SOURCES = {cls.name: cls for cls in [TaiwanJobs, Job104, Yourator, Cake, Remotive, RemoteOK, Arbeitnow, Himalayas, HackerNewsHiring]}
