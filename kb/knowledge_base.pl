% ============================================================
% knowledge_base.pl
% Knowledge Base del progetto Logistica Flotta Furgoni Bari
% ============================================================
% Fatti generati automaticamente (non modificare a mano):
%   flotta.pl      veicolo/7
%   clienti.pl     cliente/3, finestra/3, ubicazione/2
%   ztl_nodi.pl    in_ztl/1
%   previsioni.pl  scarico_previsto/2, prob_mancata/2   (output del modulo ML)
%
% Rappresentazione delle date: data(Giorno, Mese, Anno).
% Orari: minuti dalla mezzanotte (es. 450 = 07:30).
% ============================================================

:- dynamic scarico_previsto/2.
:- dynamic prob_mancata/2.
:- discontiguous violazione/1.

:- consult('flotta.pl').
:- consult('clienti.pl').
:- consult('ztl_nodi.pl').
:- prolog_load_context(directory, Dir),
   atom_concat(Dir, '/previsioni.pl', File),
   (exists_file(File) -> consult(File) ; true).
% NB: grafo.pl (nodi e archi) non viene caricato: con ~92K fatti la ricerca su
% grafo e' delegata ad A* in Python; la KB fornisce ad A* i vincoli di transito.


% ============================================================
% 1. TASSONOMIA DEI VEICOLI (gerarchia di classi)
% ============================================================

sottoclasse(furgone_compatto, veicolo_commerciale_leggero).
sottoclasse(furgone_grande,   veicolo_commerciale_leggero).
sottoclasse(veicolo_commerciale_leggero, veicolo_commerciale).
sottoclasse(veicolo_commerciale, veicolo).

% is_a/2: chiusura transitiva (ricorsiva) di sottoclasse/2
is_a(X, Y) :- sottoclasse(X, Y).
is_a(X, Z) :- sottoclasse(X, Y), is_a(Y, Z).

% Classificazione: la classe di un veicolo si DERIVA dai suoi attributi
% (portata e volume), non e' scritta nei dati.
classe_veicolo(V, furgone_compatto) :-
    veicolo(V, _, Cap, Vol, _, _, _), Cap =< 1000, Vol =< 5.
classe_veicolo(V, furgone_grande) :-
    veicolo(V, _, Cap, _, _, _, _), Cap > 1000.

% istanza(V, C): V appartiene alla classe C o a una sua superclasse
istanza(V, C) :- classe_veicolo(V, C).
istanza(V, C) :- classe_veicolo(V, C0), is_a(C0, C).


% ============================================================
% 2. TASSONOMIA DELLE STRADE, VELOCITA' E DIVIETI DI TRANSITO
% ============================================================
% categoria(TipoOSM, Categoria)

categoria(motorway, scorrimento).        categoria(motorway_link, scorrimento).
categoria(trunk, scorrimento).           categoria(trunk_link, scorrimento).
categoria(primary, scorrimento).         categoria(primary_link, scorrimento).
categoria(secondary, quartiere).         categoria(secondary_link, quartiere).
categoria(tertiary, quartiere).          categoria(tertiary_link, quartiere).
categoria(residential, locale).          categoria(unclassified, locale).
categoria(living_street, ristretta).     categoria(service, ristretta).

% Velocita' di riferimento (km/h) per tipo di strada in ambito urbano
velocita_base(motorway, 90).      velocita_base(motorway_link, 60).
velocita_base(trunk, 70).         velocita_base(trunk_link, 50).
velocita_base(primary, 50).       velocita_base(primary_link, 40).
velocita_base(secondary, 45).     velocita_base(secondary_link, 35).
velocita_base(tertiary, 40).      velocita_base(tertiary_link, 30).
velocita_base(residential, 30).   velocita_base(unclassified, 30).
velocita_base(living_street, 20). velocita_base(service, 20).

% Default ed eccezioni: per default un veicolo percorre una strada alla
% velocita' base; l'eccezione limitazione/3 la riduce per alcune classi.
velocita(V, Tipo, Kmh) :-
    veicolo(V, _, _, _, _, _, _), velocita_base(Tipo, Kmh),
    \+ limitazione(V, Tipo, _).
velocita(V, Tipo, Kmh) :-
    velocita_base(Tipo, K0), limitazione(V, Tipo, K1),
    Kmh is min(K0, K1).

% I furgoni grandi sono piu' lenti nelle strade strette di quartiere
limitazione(V, Tipo, 25) :- istanza(V, furgone_grande), categoria(Tipo, locale).
limitazione(V, Tipo, 15) :- istanza(V, furgone_grande), categoria(Tipo, ristretta).

% Divieto di transito: i furgoni grandi non attraversano le zone residenziali
% (living_street) se non per raggiungere la destinazione (gestito da A*).
vietata(V, living_street) :- istanza(V, furgone_grande).

puo_percorrere(V, Tipo) :-
    veicolo(V, _, _, _, _, _, _), velocita_base(Tipo, _), \+ vietata(V, Tipo).


% ============================================================
% 3. CALENDARIO
% ============================================================

festa_nazionale(1, 1).   festa_nazionale(6, 1).   festa_nazionale(25, 4).
festa_nazionale(1, 5).   festa_nazionale(2, 6).   festa_nazionale(15, 8).
festa_nazionale(1, 11).  festa_nazionale(8, 12).  festa_nazionale(25, 12).
festa_nazionale(26, 12).
festa_nazionale(6, 12).  % San Nicola (patrono di Bari, festa liturgica)

% Eventi cittadini con forti limitazioni al traffico nel centro
evento_cittadino(corteo_storico_san_nicola, 7, 5).
evento_cittadino(festa_traslazione_san_nicola, 8, 5).

% day_of_the_week/2 (libreria SWI): 1 = lunedi' ... 7 = domenica
giorno_settimana(data(G, M, A), DoW) :- day_of_the_week(date(A, M, G), DoW).

festivo(data(G, M, _)) :- festa_nazionale(G, M).
festivo(D) :- giorno_settimana(D, 7).

% Tipo di giorno con priorita' evento > festivo > feriale (negazione come fallimento)
tipo_giorno(data(G, M, _), evento) :- evento_cittadino(_, G, M).
tipo_giorno(D, festivo) :- \+ tipo_giorno(D, evento), festivo(D).
tipo_giorno(D, feriale) :- \+ tipo_giorno(D, evento), \+ festivo(D).


% ============================================================
% 4. ZTL: ORARI, PERMESSI, ACCESSO
% ============================================================

% fascia_ztl(TipoGiorno, Inizio, Fine): intervallo [Inizio, Fine) di ZTL attiva
fascia_ztl(feriale, 450, 1200).   % 07:30 - 20:00
fascia_ztl(festivo, 600, 1380).   % 10:00 - 23:00
fascia_ztl(evento, 0, 1440).      % tutto il giorno

% Durante gli eventi il permesso vale solo nella fascia di carico/scarico
fascia_carico_scarico(420, 600).  % 07:00 - 10:00

% Il permesso ZTL per il trasporto merci spetta ai soli mezzi compatti
permesso_ztl(V) :- istanza(V, furgone_compatto).

ztl_attiva(D, Min) :-
    tipo_giorno(D, T), fascia_ztl(T, I, F), Min >= I, Min < F.

permesso_sospeso(D, Min) :-
    tipo_giorno(D, evento),
    fascia_carico_scarico(I, F), \+ (Min >= I, Min < F).

% accesso_ztl(V, D, Min): V puo' trovarsi in ZTL il giorno D al minuto Min
accesso_ztl(_, D, Min) :- \+ ztl_attiva(D, Min).
accesso_ztl(V, D, Min) :-
    ztl_attiva(D, Min), permesso_ztl(V), \+ permesso_sospeso(D, Min).

cliente_in_ztl(C) :- ubicazione(C, N), in_ztl(N).


% ============================================================
% 5. FINESTRE DI CONSEGNA EFFETTIVE (ragionamento su intervalli)
% ============================================================

turno_lavoro(480, 1020).          % 08:00 - 17:00

% intervallo_accesso(V, C, D, I, F): intervalli in cui V puo' raggiungere C
intervallo_accesso(_, C, _, 0, 1440) :-
    \+ cliente_in_ztl(C).
intervallo_accesso(_, C, D, 0, ZI) :-
    cliente_in_ztl(C), tipo_giorno(D, T), fascia_ztl(T, ZI, _), ZI > 0.
intervallo_accesso(_, C, D, ZF, 1440) :-
    cliente_in_ztl(C), tipo_giorno(D, T), fascia_ztl(T, _, ZF), ZF < 1440.
intervallo_accesso(V, C, D, ZI, ZF) :-
    cliente_in_ztl(C), permesso_ztl(V),
    tipo_giorno(D, T), T \== evento, fascia_ztl(T, ZI, ZF).
intervallo_accesso(V, C, D, I, F) :-
    cliente_in_ztl(C), permesso_ztl(V),
    tipo_giorno(D, evento), fascia_carico_scarico(I, F).

% finestra_effettiva(V, C, D, I, F): intersezione non vuota tra finestra
% richiesta dal cliente, intervallo di accesso del veicolo e turno di lavoro
finestra_effettiva(V, C, D, I, F) :-
    veicolo(V, _, _, _, _, _, _),
    finestra(C, CI, CF),
    turno_lavoro(TI, TF),
    intervallo_accesso(V, C, D, AI, AF),
    I is max(CI, max(AI, TI)),
    F is min(CF, min(AF, TF)),
    I < F.

servibile(C) :- ubicazione(C, _).

% idoneo(V, C, D): V puo' servire C il giorno D (esiste una finestra effettiva)
idoneo(V, C, D) :-
    servibile(C), veicolo(V, _, _, _, _, _, _),
    once(finestra_effettiva(V, C, D, _, _)).

veicoli_idonei(C, D, Lista) :- findall(V, idoneo(V, C, D), Lista).


% ============================================================
% 6. CONOSCENZA APPRESA (integrazione con il modulo ML)
% ============================================================

tempo_scarico_standard(10).       % Tempo_Scarico_Previsto_min del dataset
soglia_preavviso(0.5).

% Durata del servizio: previsione ML se disponibile, altrimenti default
durata_servizio(C, M) :- scarico_previsto(C, M).
durata_servizio(C, M) :- \+ scarico_previsto(C, _), tempo_scarico_standard(M).

% Clienti da contattare prima della consegna (alto rischio di assenza)
richiede_preavviso(C) :-
    prob_mancata(C, P), soglia_preavviso(S), P >= S.


% ============================================================
% 7. SPIEGAZIONI
% ============================================================
% dimostra(Goal, Albero) restituisce l'albero di prova del goal: mostra
% quali fatti e quali regole sono stati usati, ed e' lo strumento usato per
% il debugging a livello di conoscenza (risposte errate o mancanti).

dimostra(true, true) :- !.
dimostra((A, B), (PA, PB)) :- !, dimostra(A, PA), dimostra(B, PB).
dimostra(\+ A, non(A)) :- !, \+ dimostra(A, _).
dimostra(once(G), P) :- !, once(dimostra(G, P)).
dimostra(G, sistema(G)) :- predicate_property(G, built_in), !, call(G).
dimostra(G, sistema(G)) :- predicate_property(G, imported_from(_)), !, call(G).
dimostra(G, fatto(G)) :- predicate_property(G, number_of_rules(0)), !, clause(G, true).
dimostra(G, regola(G, P)) :- clause(G, Corpo), dimostra(Corpo, P).

% perche_non_idoneo(V, C, D, Motivo): motivo per cui idoneo(V, C, D) fallisce
perche_non_idoneo(_, C, _, fuori_area_servita) :-
    \+ servibile(C).
perche_non_idoneo(_, C, _, finestra_fuori_turno) :-
    servibile(C), finestra_fuori_turno(C).
perche_non_idoneo(V, C, D, ztl_senza_permesso) :-
    servibile(C), \+ finestra_fuori_turno(C),
    cliente_in_ztl(C), \+ permesso_ztl(V),
    veicolo(V, _, _, _, _, _, _), \+ finestra_effettiva(V, C, D, _, _).
perche_non_idoneo(V, C, D, permesso_sospeso_per_evento) :-
    servibile(C), \+ finestra_fuori_turno(C),
    cliente_in_ztl(C), permesso_ztl(V), tipo_giorno(D, evento),
    \+ finestra_effettiva(V, C, D, _, _).

% la finestra richiesta non interseca il turno di lavoro
finestra_fuori_turno(C) :-
    finestra(C, I, F), turno_lavoro(TI, TF), (F =< TI ; I >= TF).


% ============================================================
% 8. VINCOLI D'INTEGRITA' (debugging a livello di conoscenza)
% ============================================================
% violazione(X) e' derivabile solo se la KB e' incoerente: una KB corretta
% non ne deve derivare nessuna (verificato dai test).

violazione(finestra_vuota(C)) :- finestra(C, I, F), I >= F.
violazione(cliente_senza_finestra(C)) :- cliente(C, _, _), \+ finestra(C, _, _).
violazione(veicolo_non_classificato(V)) :-
    veicolo(V, _, _, _, _, _, _), \+ classe_veicolo(V, _).
violazione(classe_ambigua(V)) :-
    classe_veicolo(V, A), classe_veicolo(V, B), A @< B.
violazione(ubicazione_fuori_area(C)) :-
    ubicazione(C, _), cliente(C, Citta, _), Citta \== bari.
violazione(ubicazione_multipla(C)) :-
    ubicazione(C, N1), ubicazione(C, N2), N1 @< N2.
violazione(tipo_strada_senza_categoria(T)) :-
    velocita_base(T, _), \+ categoria(T, _).
violazione(probabilita_non_valida(C)) :-
    prob_mancata(C, P), (P < 0 ; P > 1).

violazioni(L) :- findall(X, violazione(X), L).
