import sys
from core import ask

question = " ".join(sys.argv[1:])
print(ask(question).model_dump_json(indent=2))