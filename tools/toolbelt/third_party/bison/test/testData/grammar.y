%token NUMBER
%%
input: NUMBER ;
%%
int yyerror(const char *s) { return 0; }
int yylex(void) { return 0; }
