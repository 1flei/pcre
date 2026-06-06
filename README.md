# pcre

Compile-time regex engine for [PythoC](https://github.com/1flei/PythoC).

Parses regex patterns at Python compile time, builds a Tagged NFA -> TDFA -> Tagged Boyer-Moore automaton, and generates native `@compile` functions with LLVM codegen via PythoC.

## Quick start

```python
from pcre import compile

r = compile("[a-z]+@[a-z]+\\.[a-z]+")
r.match(b"foo@bar.com")             # (True, {})
r.search(b"email: a@b.c")           # (True, {'start': 7, 'end': 12})
```

## Pipeline

```
pattern -> parse (AST) -> TNFA -> TDFA -> TaggedOPCSBMA -> AST -> meta.compile_generated -> LLVM native code
```

## Dependencies

- `pythoc`
