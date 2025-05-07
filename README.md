# uecprds

A lightweight Python class for sending simple UECP RDS commands over a serial connection.

Created by reverse-engineering the serial communication of the "EP-RDS v1.2" Windows tool by *Klabautermann*.

Tested with the Profline SFM RDS built-in encoder, but it should also work with other RDS encoders that conform to the UECP protocol.

---

## Features

- Set PI, PS, Radiotext, PTY, TP, TA, and MS flags
- Builds and sends properly framed UECP messages
- Includes byte-stuffing and CRC-16-CCITT checksum
- Simple and readable serial communication
- Suitable for automation and command-line integration

---

## Requirements

- Python 3
- `pyserial` library

To install the required library on Ubuntu / Debian:

```bash
sudo apt install python3-serial
```

## Installation

Clone the repository:

```sh
git clone https://github.com/yourusername/uecprds.git
cd uecprds
```

## Execution

If needed change the example.py code.

Run the example:

```sh
python3 example.py
```

