"""mqtt_config.py - broker settings shared by the pilot publisher and subscriber."""
import os

# IPv4 address on purpose: "localhost" tries IPv6 (::1) first, and the WSL port
# forward only answers on 127.0.0.1 (the Test-NetConnection check showed this).
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
TOPIC_PREFIX = "energy/meters"     # the publisher adds /{meter_id}
TOPIC_FILTER = "energy/meters/#"   # the subscriber receives every meter's topic
QOS = 1                            # at-least-once delivery, as the assignment requires
PILOT_SIZE = 2000                  # number of readings taken from the generator

# Broker login, read from environment variables so no secret is stored in code.
# EMQX refused anonymous clients ("Not authorized"), so a user was created in its dashboard.
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")