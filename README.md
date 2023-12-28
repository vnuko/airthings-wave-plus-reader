# Airthings Wave Plus Data Reader

## Project Description

The Airthings Wave Plus Data Reader is a Python project designed to read data from one or multiple Airthings Wave Plus devices and store the results in a JSON file. This project utilizes the Bleak Bluetooth library to communicate with the devices and collect various measurements including temperature, humidity, CO2 levels, and more.

## Installation and Dependencies

This project requires the Bleak library to communicate with Bluetooth devices. You can install it using pip:

```bash
pip install bleak
```

## Usage
Ensure your system supports Bluetooth Low Energy (BLE).
Run the provided Python script to scan for Airthings Wave Plus devices and collect data.

```bash
python3 wave-plus-reader.py
```

if run correctly, new json file (wave_plus_data.json) with measurements is generated on the project level.

## Next Steps (TODO)
As a future enhancement, consider adding a simple web server component to the project. This server could read the generated JSON file and display the collected measurements as responses to incoming requests.


