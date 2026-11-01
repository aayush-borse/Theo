from .text import TextProvider
from .tabular import TabularProvider
from .image import ImageProvider
from .document import DocumentProvider
from .media import MediaProvider

PROVIDERS={}
for provider in (TextProvider(), TabularProvider(), ImageProvider(), DocumentProvider(), MediaProvider()):
    for modality in provider.supported_modalities: PROVIDERS[modality]=provider
