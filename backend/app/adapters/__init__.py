from app.adapters.base import BaseEventSourceAdapter, SourceFetchResult
from app.adapters.devfolio import DevfolioAdapter
from app.adapters.unstop import UnstopAdapter
from app.adapters.mlh import MLHAdapter
from app.adapters.devpost import DevpostAdapter

ADAPTERS = {
    "devfolio": DevfolioAdapter(),
    "devpost": DevpostAdapter(),
    "mlh": MLHAdapter(),
    "unstop": UnstopAdapter(),
}

def get_all_adapters():
    return list(ADAPTERS.values())

def get_adapter(name: str) -> BaseEventSourceAdapter | None:
    return ADAPTERS.get(name.strip().lower())
