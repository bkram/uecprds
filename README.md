# uecprds

UECPRDS provides a small Python library and helper daemon for sending UECP RDS
commands over a serial connection.

It implements a framing method that was reverse-engineered from the
**"EP-RDS v1.2"** Windows tool by *Klabautermann*. Because of this, it
might not conform exactly to the official UECP specification.

Tested with the **Profline SFM RDS** built-in encoder, but it should
also work with other RDS encoders that conform to the UECP protocol.

---

## ✨ Features

- Configure RDS parameters like **PI**, **PS**, **Radiotext**, **PTY**, **TP**, **TA**, and **MS** flags.
- Build and send properly framed **UECP messages**.
- Uses simple byte-stuffing by inserting `0xFD` after every `0xFE` or `0xFF` (not the usual UECP escape sequence) and computes a **CRC-16-CCITT**.
- Simple and readable **serial communication**.
- Suitable for **automation** and **command-line integration**.
- A ready to use daemon (`rdsd.py`) periodically sends Radiotext and Program Service data based
  on a YAML configuration file.


---

## 📋 Requirements

- **Python 3**
- **`pyserial` library**

To install the required library on Ubuntu/Debian:

```bash
sudo apt install python3-serial
```

---

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/bkram/uecprds.git
cd uecprds
```

---

## ▶️ Usage

1. Create or modify a YAML configuration file. A sample is provided in
   `examples/veronica.yml`.
2. Start the daemon with the configuration:

```bash
python3 rdsd.py --cfg examples/veronica.yml
```

### Configuration

The YAML file controls all RDS parameters. Below is an excerpt from
`examples/veronica.yml` demonstrating the optional `radiotext_file` key.
When set, `rdsd.py` watches this file and immediately sends its contents as
Radiotext whenever the file changes.

```yaml
# 💬 RT (Radiotext) Settings
radiotext_messages:
  - "VERONICA"
  - "JOIN THE CLUB"
center_radiotext_display: true
radiotext_file: radiotext.txt
radiotext_change_interval_seconds: 8
```

---

## 📖 Library Example

The snippet below shows how to use the `UECPRDS` class directly:

```python
from uecprds import UECPRDS

# Create UECPRDS instance
rds = UECPRDS(
    port="/dev/ttyUSB0",
    baudrate=9600,
    delay=2.0,
    pi=0x1234,
    ps="ITALO FM",
    rt="Now playing: Italo Disco Hits",
    pty=10,
    ms=True,
    tp=False,
    ta=False,
)

# Send all RDS frames to the serial device
rds.send_all()
```

---

## 🛠️ Development

Feel free to contribute to this project by submitting issues or pull requests.

---

## 📜 License

This project is licensed under the **GNU General Public License v2.0**. See the [LICENSE](LICENSE) file for details.
