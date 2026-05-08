import getpass
import platform
import socket


def build_identity_payload(
    hostname: str | None = None,
    username: str | None = None,
) -> dict[str, str]:
    return {
        "service": "agent_private",
        "hostname": hostname or socket.gethostname(),
        "username": username or getpass.getuser(),
        "os": platform.system(),
    }


def main() -> None:
    print(build_identity_payload())


if __name__ == "__main__":
    main()
