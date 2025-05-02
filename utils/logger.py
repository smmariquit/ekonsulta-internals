import logging

def setup_logger(log_file="discord.log", log_level=logging.INFO):
    """
    Sets up the logger for the application.

    Args:
        log_file (str): Path to the log file.
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG).
    """
    logging.basicConfig(
        filename=log_file,
        filemode="a",  # Append to the log file
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=log_level,
    )
    logging.getLogger().addHandler(logging.StreamHandler())  # Also log to console
