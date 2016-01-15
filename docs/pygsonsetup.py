def setup(sphinx):
    from pygson.json_lexer import JSONLexer
    sphinx.add_lexer("json", JSONLexer())