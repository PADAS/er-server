#!/usr/bin/env python3
import sys

import redis

def check_sentinel_and_exit(options):

    redis_client = redis.from_url(options.redis_url)

    if not redis_client.exists(options.sentinel_key):
        sys.exit(1)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(allow_abbrev=True)
    parser.add_argument('--sentinel_key', '-k',
                        action='store',
                        help='Sentinel key to look for in Redis.',
                        default='celerybeat-pulse-sentinel')

    parser.add_argument('--redis_url', '-r',
                        action='store',
                        help='URL for Redis DB.',
                        default='redis://redis:6379')

    options = parser.parse_args()
    check_sentinel_and_exit(options)
