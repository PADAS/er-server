#!/usr/bin/env python3
import sys

from das_server.pubsub import get_pool

pool = get_pool()
try:
    # Make connection
    conn = pool.connection
    conn.connect()
    if conn.connected:
        conn.release()
        sys.exit(0)
except Exception:
    # Kombu connection not established
    sys.exit(1)
