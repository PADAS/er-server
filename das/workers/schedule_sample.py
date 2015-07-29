__author__ = 'chris'
import schedule
import time

from workers.usingrq.manager import queue_count

URLS = ['http://chrisdoehring.com', 'http://vulcan.com']
def job():



    if len(URLS) > 0:
        queue_count(URLS.pop(0))


schedule.every(5).seconds.do(job)


while True:
    schedule.run_pending()
    time.sleep(1)