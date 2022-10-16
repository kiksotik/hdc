"""
Showcases the resetting of features.

This script has been used to investigate the resetting behavior.
"""
import logging
import time

from minimal_proxy import MinimalDevice

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(levelname)7s - %(name)s - %(message)s', datefmt='%M:%S')
ch.setFormatter(formatter)
logger = logging.getLogger("HDC")
logger.setLevel(logging.DEBUG)
logger.addHandler(ch)
logging.getLogger("HDC.packetizer").setLevel(logging.INFO)
logging.getLogger("HDC.protocol").setLevel(logging.INFO)
logging.getLogger("HDC.proxy").setLevel(logging.INFO)

dev = MinimalDevice(connection_url="COM10")
dev.protocol.connect()

logger.info("____________________________________")
logger.info("Resetting the Core-feature...")
dev.core.cmd_reset()
time.sleep(1)

logger.info("____________________________________")
logger.info("Resetting the Core-feature, again...")
dev.core.cmd_reset()
time.sleep(1)

dev.protocol.close()
