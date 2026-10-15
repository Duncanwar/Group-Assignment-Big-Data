"""pilot_publisher.py - Task 1.3.1: publish the first 2,000 generator readings over MQTT (QoS 1)."""
import itertools
import json
import logging
import os
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt

import smart_meter_simulator as sim          # the unchanged generator
from mqtt_config import BROKER_HOST, BROKER_PORT, TOPIC_PREFIX, QOS, PILOT_SIZE, MQTT_USER, MQTT_PASSWORD

ACK_TIMEOUT = 60       # seconds to wait for the last receipts after the final publish
PACE_SECONDS = 0.005   # pause after each message: about 200 messages/s instead of ~3,000/s,
                       # so the broker's per-subscriber queue is never overrun

os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/pilot_publisher.log", mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console],
                    format="%(asctime)s %(levelname)s %(message)s")

counts = {"taken": 0, "published": 0, "publish_failed": 0, "acked": 0}
connected = threading.Event()                # set once the broker accepts our connection


def now_cat():
    # Local time with its offset (+02:00 = CAT), for the execution-time record.
    return datetime.now().astimezone().isoformat(timespec="seconds")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        logging.error("Connection refused by broker: %s", reason_code)
        return
    logging.info("Connected to broker")
    connected.set()


def on_publish(client, userdata, mid, reason_code, properties):
    # With QoS 1 this fires when the broker's PUBACK (receipt) for message `mid` arrives.
    counts["acked"] += 1


def main():
    logging.info("=== publisher run started %s (pace %.3f s per message) ===", now_cat(), PACE_SECONDS)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-publisher")
    client.on_connect = on_connect
    client.on_publish = on_publish
    if MQTT_USER:                                   # send the broker login when configured
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    if not connected.wait(timeout=10):
        logging.error("Could not connect to the broker within 10 s. Is EMQX running?")
        return

    start = time.perf_counter()
    # islice takes exactly the first PILOT_SIZE dictionaries; the generator never runs further.
    for record in itertools.islice(sim.iter_readings(), PILOT_SIZE):
        counts["taken"] += 1
        topic = f"{TOPIC_PREFIX}/{record['meter_id']}"   # energy/meters/{meter_id}
        payload = json.dumps(record)                      # dictionary -> JSON text
        info = client.publish(topic, payload, qos=QOS, retain=False)   # QoS 1, NOT retained
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            counts["published"] += 1
        else:
            counts["publish_failed"] += 1
            logging.error("PUBLISH FAILED rc=%s topic=%s", info.rc, topic)
        logging.debug("sent mid=%s topic=%s event_time=%s", info.mid, topic, record["event_time"])
        time.sleep(PACE_SECONDS)                          # pace the stream

    # Wait for the broker's receipts for everything we sent.
    deadline = time.time() + ACK_TIMEOUT
    while counts["acked"] < counts["published"] and time.time() < deadline:
        time.sleep(0.2)
    elapsed = time.perf_counter() - start

    client.loop_stop()
    client.disconnect()

    logging.info("---------------- PUBLISHER SUMMARY ----------------")
    logging.info("Finished at (CAT)                    : %s", now_cat())
    logging.info("Pacing per message (seconds)         : %.3f", PACE_SECONDS)
    logging.info("Dictionaries taken from generator    : %d", counts["taken"])
    logging.info("Messages handed to the client        : %d", counts["published"])
    logging.info("Publish failures                     : %d", counts["publish_failed"])
    logging.info("Messages acknowledged by broker      : %d", counts["acked"])
    logging.info("Elapsed seconds                      : %.1f", elapsed)


if __name__ == "__main__":
    main()