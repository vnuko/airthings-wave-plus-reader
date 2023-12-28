import asyncio
import json
import logging
import math
import struct
from datetime import datetime

from bleak import BleakClient
from bleak import BleakScanner

# Airthings Wave Plus Command UUIDS
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
COMMAND_UUID = "b42e2d06-ade7-11e4-89d3-123b93f75cba"


class WavePlusReader:
    found_devices = []
    command_data = None

    def __init__(self):
        self.logger = logging.getLogger(__name__ + "." + self.__class__.__name__)

    # Discovers Airthings devices.

    # Args:
    #     scans (int): Number of scan iterations.
    #     timeout (int): Timeout for each scan iteration.

    # Returns:
    #     int: The number of Airthings devices found.
    async def discover(self, scans=2, timeout=5):
        self.logger.info("Searching for Devices...")

        for scn in range(scans):
            devices = await BleakScanner.discover(timeout)
            for device in devices:
                # The manufacturer_data attribute contains vendor-specific device data,
                # For all Airthings devices the ID is 820 / 0x0334
                if 0x0334 in device.metadata['manufacturer_data']:
                    if len(self.found_devices) == 0 or any(
                            found_device.address != device.address for found_device in self.found_devices):
                        self.print_discovered(device)
                        self.found_devices.append(device)

        self.logger.info("Total {0} device(s) found".format(len(self.found_devices)))

        return len(self.found_devices)

    async def connect(self, device):
        async with BleakClient(device.address, use_cached=False) as client:
            # Read services of the discovered device
            services = await client.get_services()
            if services:
                formatted_data = await self.read_and_format(client, list(services))
            else:
                formatted_data = {}

        return formatted_data

    def get_found_devices(self):
        return self.found_devices

    def print_discovered(self, device):
        self.logger.info("Discovered {0} Device: {1} RSSI: {2}".format(device.name, device.address, device.rssi))

    async def read_and_format(self, client, services):
        measurements = await self.read_measurements(client)
        serial_number = await self.read_serial_number(client)
        command_data = await self.read_command_data(client)

        formatted_data = {}
        formatted_data['radon_day_average'] = measurements[4]
        formatted_data['radon_total_average'] = measurements[5]
        formatted_data['temperature'] = measurements[6] / 100.0
        formatted_data['pressure'] = measurements[7] / 50.0
        formatted_data['co2'] = measurements[8] * 1.0
        formatted_data['voc'] = measurements[9] * 1.0
        formatted_data['timestamp'] = str(datetime.isoformat(datetime.utcnow()))
        formatted_data['serial_no'] = serial_number
        formatted_data['illuminance'] = command_data['illuminance']
        formatted_data['battery_voltage'] = command_data['battery_voltage']
        formatted_data['battery_percentage'] = command_data['battery_percentage']
        formatted_data['humidity_rel'] = measurements[1] / 2.0
        formatted_data['humidity_abs'] = self.calc_absolute_humidity(
            formatted_data['humidity_rel'],
            formatted_data['temperature'],
            formatted_data['pressure']
        )

        return formatted_data

    async def read_measurements(self, client):
        self.logger.info("Reading Measurements...")
        byte_measurements = await client.read_gatt_char(CHARACTERISTIC_UUID)
        return struct.unpack("<4B8H", byte_measurements)

    async def read_serial_number(self, client):
        self.logger.info("Reading Serial & Model Number")
        model_number = await client.read_gatt_char(MODEL_NUMBER_UUID)
        serial_number = await client.read_gatt_char(SERIAL_NUMBER_UUID)

        return model_number.decode('utf-8') + serial_number.decode('utf-8')

    async def read_command_data(self, client):
        event = asyncio.Event()

        await client.start_notify(COMMAND_UUID, self.command_data_handler)
        await client.write_gatt_char(COMMAND_UUID, struct.pack('<B', 0x6d))

        formatted_command_data = {}
        formatted_command_data['illuminance'] = 0
        formatted_command_data['battery_voltage'] = 0
        formatted_command_data['battery_percentage'] = 0

        try:
            await asyncio.wait_for(event.wait(), 2)  # 2 sec.
        except asyncio.TimeoutError:
            self.logger.info("Timeout on command data.")

        if self.command_data is not None:
            raw_command_data = struct.unpack("<L12B6H", self.command_data[2:])
            formatted_command_data['illuminance'] = raw_command_data[2]
            formatted_command_data['battery_voltage'] = raw_command_data[17] / 1000.0
            voltage_max = 3.2
            voltage_min = 2.2
            formatted_command_data['battery_percentage'] = max(0, min(100, round(
                (formatted_command_data['battery_voltage'] - voltage_min) / (voltage_max - voltage_min) * 100)))
        await client.stop_notify(COMMAND_UUID)

        return formatted_command_data

    def command_data_handler(self, sender, data):
        self.logger.info("Reading Command Data")
        self.command_data = data

    # Absolute Humidity Calculation:
    # formula: https://planetcalc.com/2167/
    # rh: Relative Humidity
    # t: temperature
    # p: barometric pressure
    # returns: absolute humidity in g/m3
    def calc_absolute_humidity(self, rh, t, p):
        svp = self.calc_saturation_vapor_pressure(t, p)
        ah = (rh * svp) / (461.5 * (t + 273.15))

        return ah * 1000

    # Saturation vapor pressure
    # formula: https://planetcalc.com/2161/
    # t: temperature
    # p: barometric pressure
    # returns: pressure value in hectopascals (hPa). 1 hectopascal = 100 pascals
    @staticmethod
    def calc_saturation_vapor_pressure(t, p):
        ewt = 6.112 * math.exp((17.62 * t) / (243.12 + t))
        fp = 1.0016 + 3.15 * math.pow(10, -6) * p - 0.074 / p

        return fp * ewt

    @staticmethod
    def store_data_as_json(data):
        with open("wave_plus_data.json", "w") as file:
            json.dump(data, file, indent=4)


async def main():
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    reader = WavePlusReader()
    no_of_found_devices = await reader.discover()

    if no_of_found_devices > 0:
        measurements_data = []
        found_devices = reader.get_found_devices()
        for device in found_devices:
            formatted_data = await reader.connect(device)
            measurements_data.append({
                "device_name": device.name,
                "measurements": formatted_data  # Replace this with actual measurements
            })

            logger.info("All Data Received")
            logger.info(formatted_data)

        reader.store_data_as_json(measurements_data)


if __name__ == "__main__":
    asyncio.run(main())
