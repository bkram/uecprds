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

- Configure RDS parameters like **PI**, **PS**, **Radiotext**, **PTY**, **TP**, **TA**, and **MS** flags. You can also provide
  **Alternative Frequencies (AF)** that will be sent to the encoder.
- Build and send properly framed **UECP messages**.
- Uses simple byte-stuffing by inserting `0xFD` after every `0xFE` or `0xFF` (not the usual UECP escape sequence) and computes a **CRC-16-CCITT**.
- Simple and readable **serial communication**.
- Suitable for **automation** and **command-line integration**.
- A ready to use daemon (`rdsd.py`) periodically sends Radiotext and Program Service data based
  on a YAML configuration file.


---

## 📋 Requirements

- **Python 3**
- **`pyserial` and `pyyaml` libraries**

Install the dependencies with `pip`:

```bash
pip install -r requirements.txt
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
   `examples/config.yml`.
2. Start the daemon with the configuration:

```bash
python3 rdsd.py --cfg examples/config.yml
```

### Configuration

The YAML file controls all RDS parameters. Below is an excerpt from
`examples/config.yml` demonstrating the optional `file` key in the
`display.rt` section. When set, `rdsd.py` watches this file and immediately
sends its contents as Radiotext whenever the file changes.

To broadcast **Alternative Frequencies (AF)**, enable the `af` section and
provide a list of frequencies under the `alternate_frequencies` key.

```yaml
# 📻 Alternate Frequencies
af:
  enable: true
  alternate_frequencies:
    - 92.4
    - 93.9

# 💬 RT (Radiotext) Settings
display:
  rt:
    messages:
      - "VERONICA"
      - "JOIN THE CLUB"
    center: true
    file: radiotext.txt
    change_interval_seconds: 8
```
---
## 🛠️ Development

Feel free to contribute to this project by submitting issues or pull requests.

---

## 📜 License

This project is licensed under the **GNU General Public License v2.0**. See the [LICENSE](LICENSE) file for details.
