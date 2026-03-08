def main() -> int:
    from .app import main as run_main

    return run_main()


__all__ = ["main"]
