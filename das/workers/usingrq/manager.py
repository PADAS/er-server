from redis import Redis
from rq import Queue
import time
q = Queue(connection=Redis())

from workers.usingrq.tasks import *

def queue_count(url):
    job = q.enqueue(count_words_at_url, url)


