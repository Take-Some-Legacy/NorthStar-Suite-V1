%{
int yylex(void); void yyerror(const char *s) { }
%}
%token NUM
%%
input: NUM ;
%%
