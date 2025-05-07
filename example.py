from uecprds import UECPRDS

# Create UECPRDS instance with an Italo-inspired PS name
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
