# Blauberg Vento API

A Python library for controlling Blauberg Vento Expert Wi-Fi ventilation units.

## Features

- Control Blauberg Vento fans via UDP protocol
- Support for both synchronous and asynchronous operations
- Device discovery on local network
- Comprehensive parameter control (speed, timers, sensors, Wi-Fi, etc.)
- Full device state retrieval

## Installation

```bash
pip install blauberg-vento
```

# Usage

## Synchronous Client
from blauberg_vento import VentoClient

# Create client
```python
client = VentoClient(
    host="192.168.1.100",
    device_id="YOUR_DEVICE_ID",
    password="1111"
)

# Get device state
state = client.get_state()
print(f"Power: {'ON' if state.power else 'OFF'}")
print(f"Speed: {state.speed_name}")
print(f"Mode: {state.operation_mode_name}")

# Control device
client.turn_on()
client.set_speed(2)  # Speed 2
client.set_ventilation()  # Ventilation mode
```

## Asynchronous Client
```python
import asyncio
from blauberg_vento import AsyncVentoClient

async def main():
    async with AsyncVentoClient(
        host="192.168.1.100",
        device_id="YOUR_DEVICE_ID",
        password="1111"
    ) as client:
        state = await client.get_state()
        print(f"Power: {'ON' if state.power else 'OFF'}")
        await client.turn_on()

asyncio.run(main())
```

## Device discovery
```python
from blauberg_vento import VentoClient

# Discover devices on network
devices = VentoClient.discover()
for device in devices:
    print(f"Found device: {device.device_id} at {device.ip}")
```

# Releasing

Releases are published to [PyPI](https://pypi.org/project/blauberg-vento/) automatically via GitHub Actions (trusted publishing, no tokens stored).

## Release a new version

1. Bump `version` in `pyproject.toml`
2. Commit and push to `main`
3. Create a [GitHub Release](https://github.com/BirgerKo/blauberg_vento_api/releases) with a tag matching the version (e.g. `v1.0.1`)
4. The `Publish` workflow builds the sdist and wheel and uploads them to PyPI

To dry-run the pipeline, run the `Publish` workflow manually (Actions → Publish → Run workflow); it will upload to [TestPyPI](https://test.pypi.org/) instead.

# Documentation
See ARCHITECTURE.md for detailed architecture overview.

# License
MIT License - see LICENSE for details.
