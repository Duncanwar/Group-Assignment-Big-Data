"""pilot_subscriber.py - Task 1.3.2: receive pilot messages (QoS 1) and store them in energy_live."""
import json
import logging
import os
import time

import paho.mqtt.client as mqtt

from db_config import get_connection
from mqtt_config import BROKER_HOST, BROKER_PORT, TOPIC_FILTER, QOS, MQTT_USER, MQTT_PASSWORD

IDLE_SECONDS = 15   # stop once no message has arrived for this long (after the first one)

# ---- Logging: the file gets every message, the screen gets only progress and problems ----
os.makedirs("logs", exist_ok=True)
file_handler = logging.FileHandler("logs/pilot_subscriber.log", mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console],
                    format="%(asctime)s %(levelname)s %(message)s")

# ---- Counters shared between the MQTT thread and the main thread ----
stats = {"received": 0, "inserted": 0, "parse_errors": 0, "insert_errors": 0,
         "dup_flagged": 0, "last_msg_time": None}

# One INSERT for the eight fields; %(name)s is filled from the JSON keys.
INSERT_SQL = """
    INSERT INTO energy_live
        (meter_id, event_time, received_time, power_kw, voltage_v,
         current_a, frequency_hz, energy_kwh)
    VALUES
        (%(meter_id)s, %(event_time)s, %(received_time)s, %(power_kw)s, %(voltage_v)s,
         %(current_a)s, %(frequency_hz)s, %(energy_kwh)s)
"""


def on_connect(client, userdata, flags, reason_code, properties):
    # Called when the broker answers our connection request.
    if reason_code.is_failure:
        logging.error("Connection refused by broker: %s", reason_code)
        return
    logging.info("Connected to broker. Subscribing to %s at QoS %d", TOPIC_FILTER, QOS)
    client.subscribe(TOPIC_FILTER, qos=QOS)   # subscribing here also re-subscribes after a reconnect


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    # Called when the broker confirms the subscription: now it is safe to start the publisher.
    logging.info("Subscription confirmed (%s). READY: start the publisher now.",
                 [str(rc) for rc in reason_code_list])


def on_message(client, userdata, msg):
    # Called once for every message that arrives (runs in the MQTT network thread).
    stats["received"] += 1
    stats["last_msg_time"] = time.time()
    if msg.dup:                       # the broker flags a re-delivery of an earlier message
        stats["dup_flagged"] += 1
    try:
        reading = json.loads(msg.payload.decode("utf-8"))   # JSON text -> Python dict
    except (ValueError, UnicodeDecodeError) as exc:
        stats["parse_errors"] += 1
        logging.error("PARSE ERROR topic=%s error=%s payload=%r", msg.topic, exc, msg.payload[:80])
        return
    try:
        userdata["conn"].execute(INSERT_SQL, reading)        # autocommit: committed immediately
        stats["inserted"] += 1
        logging.debug("stored topic=%s meter_id=%s event_time=%s dup=%s retain=%s",
                      msg.topic, reading.get("meter_id"), reading.get("event_time"),
                      msg.dup, msg.retain)
    except Exception as exc:
        stats["insert_errors"] += 1
        logging.error("INSERT ERROR topic=%s error=%s", msg.topic, exc)
    if stats["received"] % 500 == 0:
        logging.info("progress: received=%d inserted=%d", stats["received"], stats["inserted"])


def main():
    conn = get_connection()
    conn.autocommit = True            # every INSERT is committed on its own

    logging.info("=== subscriber run started ===")
    existing = conn.execute("SELECT count(*) FROM energy_live").fetchone()[0]
    if existing != 0:
        logging.error("energy_live already holds %d rows. Empty it first "
                      "(TRUNCATE energy_live;) so the pilot starts from zero.", existing)
        return

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-subscriber",
                         userdata={"conn": conn})
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    if MQTT_USER:                                   # send the broker login when configured
        client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()               # run the network loop in a background thread

    try:
        while True:                   # main thread just watches for silence
            time.sleep(1)
            last = stats["last_msg_time"]
            if last is not None and time.time() - last > IDLE_SECONDS:
                logging.info("No message for %d s: finishing.", IDLE_SECONDS)
                break
    except KeyboardInterrupt:
        logging.info("Stopped by user.")

    client.loop_stop()
    client.disconnect()

    # All inserts are already committed (autocommit), so this count is final.
    rows = conn.execute("SELECT count(*) FROM energy_live").fetchone()[0]
    logging.info("---------------- SUBSCRIBER SUMMARY ----------------")
    logging.info("Messages received by subscriber : %d", stats["received"])
    logging.info("  flagged as re-delivery (DUP)  : %d", stats["dup_flagged"])
    logging.info("  parse errors                  : %d", stats["parse_errors"])
    logging.info("  insert errors                 : %d", stats["insert_errors"])
    logging.info("Rows inserted                   : %d", stats["inserted"])
    logging.info("Rows in energy_live (committed) : %d", rows)
    conn.close()


if __name__ == "__main__":
    main()