

from rh56_sdk.transport import SerialTransport


def main() -> None:
    for port in SerialTransport.list_ports():
        print(port)


if __name__ == "__main__":
    main()
