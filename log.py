import logging

TRACE = 1
logging.addLevelName(TRACE, "TRACE")


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kws)


logging.Logger.trace = trace

logging.basicConfig(level=logging.WARN, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
