import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from .config_utils import AppConfig
from pathlib import Path

def setup_logging(config : AppConfig):
    log_config = config.logging
    file_config = log_config.file
    
    level_name = log_config.level.upper()
    log_level = getattr(logging, level_name, logging.INFO) 

    logging.root.setLevel(logging.DEBUG)

    if log_config.console.enabled:
        console_level_name = log_config.console.level.upper()
        console_level = getattr(logging, console_level_name, log_level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(console_fmt)
        logging.root.addHandler(console_handler)

    if file_config.enabled:
        file_level_name = file_config.level.upper()
        file_level = getattr(logging, file_level_name, logging.DEBUG)
        
        filename = file_config.path
        if isinstance(filename, str):
            filename = Path(filename)
        filename.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
                                    filename=str(filename),
                                    maxBytes=10 * 1024 * 1024,  
                                    backupCount=5, 
                                    encoding="utf-8"
                                )
        file_handler.setLevel(file_level)
        file_fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s — %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        file_handler.setFormatter(file_fmt)
        logging.root.addHandler(file_handler)
        