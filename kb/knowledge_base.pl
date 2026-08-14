% ============================================================
% knowledge_base.pl
% Knowledge Base per il progetto Logistica Flotta Furgoni Bari
% ============================================================
% Carica i fatti generati automaticamente dal parsing
% ============================================================

:- discontiguous furgone/4.
:- discontiguous permesso_ztl/1.
:- discontiguous cliente/3.
:- discontiguous nodo/3.
:- discontiguous arco/3.
:- discontiguous in_ztl/1.

% Carica i file di fatti generati
:- consult('flotta.pl').
:- consult('clienti.pl').
% NB: grafo.pl e' molto grande (5 MB, ~116K fatti).
% Per le ricerche A* usiamo il pickle Python.
% Carichiamo solo i fatti in_ztl/1, estratti separatamente.
:- consult('ztl_nodi.pl').

% ============================================================
% REGOLE ZTL
% ============================================================

% Orario ZTL attivo (formato 24h)
ztl_orario_attivo(OraInizio, MinInizio, OraFine, MinFine) :-
    OraInizio = 7, MinInizio = 30,
    OraFine = 20, MinFine = 0.

% Controlla se un orario (Ora, Minuto) cade dentro la finestra ZTL
in_orario_ztl(Ora, Minuto) :-
    ztl_orario_attivo(OI, MI, OF, MF),
    MinutiCorrente is Ora * 60 + Minuto,
    MinutiInizio is OI * 60 + MI,
    MinutiFine is OF * 60 + MF,
    MinutiCorrente >= MinutiInizio,
    MinutiCorrente =< MinutiFine.

% ============================================================
% DEROGHE FESTIVE — Corteo San Nicola (7-8 Maggio)
% ============================================================

% festa_san_nicola(Giorno, Mese): i giorni del corteo
festa_san_nicola(7, 5).
festa_san_nicola(8, 5).

% Durante San Nicola, la ZTL e' SEMPRE attiva (24h)
in_orario_ztl_san_nicola(_Ora, _Minuto, Giorno, Mese) :-
    festa_san_nicola(Giorno, Mese).

% ============================================================
% ACCESSO ZTL — Regola principale
% ============================================================

% accesso_ztl_consentito(+Veicolo, +NodoDestinazione, +Ora, +Minuto, +Giorno, +Mese)
%
% Un veicolo puo' attraversare un nodo ZTL se:
%   1. Il nodo NON e' in ZTL (sempre consentito), OPPURE
%   2. Il nodo E' in ZTL ma fuori orario ZTL (e non e' San Nicola), OPPURE
%   3. Il nodo E' in ZTL, in orario ZTL, ma il veicolo ha permesso

accesso_ztl_consentito(_Veicolo, Nodo, _Ora, _Min, _G, _M) :-
    \+ in_ztl(Nodo).

accesso_ztl_consentito(_Veicolo, Nodo, Ora, Min, Giorno, Mese) :-
    in_ztl(Nodo),
    \+ festa_san_nicola(Giorno, Mese),
    \+ in_orario_ztl(Ora, Min).

accesso_ztl_consentito(Veicolo, Nodo, _Ora, _Min, Giorno, Mese) :-
    in_ztl(Nodo),
    festa_san_nicola(Giorno, Mese),
    permesso_ztl(Veicolo).

accesso_ztl_consentito(Veicolo, Nodo, Ora, Min, _Giorno, _Mese) :-
    in_ztl(Nodo),
    in_orario_ztl(Ora, Min),
    permesso_ztl(Veicolo).

% ============================================================
% IDONEITA' VEICOLO-CLIENTE
% ============================================================

% Compatibilita' merceologica (semplificata):
% Un furgone con cella frigo puo' servire qualsiasi cliente.
% Un furgone SENZA cella frigo puo' comunque servire clienti
% (in questo dataset non c'e' un flag "richiede_frigo" sui clienti).
compatibile_frigo(_Veicolo, _Cliente).

% Vincolo di finestra temporale:
% Il veicolo deve arrivare durante l'orario richiesto dal cliente.
% L'orario e' una stringa tipo '12:00 - 14:00'.
% La verifica effettiva e' fatta in Python; qui definiamo solo la regola.
in_finestra_consegna(OraArrivo, MinArrivo, OraInizio, MinInizio, OraFine, MinFine) :-
    MinutiArrivo is OraArrivo * 60 + MinArrivo,
    MinutiI is OraInizio * 60 + MinInizio,
    MinutiF is OraFine * 60 + MinFine,
    MinutiArrivo >= MinutiI,
    MinutiArrivo =< MinutiF.

% ============================================================
% IDONEITA' COMPOSTA
% ============================================================

% furgone_idoneo(+Veicolo, +Cliente, +NodoCliente, +Ora, +Minuto, +Giorno, +Mese)
%
% Un furgone e' idoneo a servire un cliente se:
%   1. Il veicolo e' un furgone valido
%   2. Il cliente e' un cliente valido con un nodo associato
%   3. L'accesso ZTL e' consentito per quel nodo/orario
%   4. La compatibilita' merceologica e' soddisfatta
furgone_idoneo(Veicolo, Cliente, Ora, Minuto, Giorno, Mese) :-
    furgone(Veicolo, _, _, _),
    cliente(Cliente, NodoCliente, _),
    accesso_ztl_consentito(Veicolo, NodoCliente, Ora, Minuto, Giorno, Mese),
    compatibile_frigo(Veicolo, Cliente).

% ============================================================
% QUERY DI UTILITA'
% ============================================================

% Tutti i veicoli con permesso ZTL
veicoli_con_permesso(Lista) :-
    findall(V, permesso_ztl(V), Lista).

% Tutti i clienti in zona ZTL
clienti_in_ztl(Lista) :-
    findall(C, (cliente(C, Nodo, _), in_ztl(Nodo)), Lista).

% Tutti i veicoli idonei per un dato cliente in un dato momento
veicoli_idonei_per_cliente(Cliente, Ora, Min, G, M, Lista) :-
    findall(V, furgone_idoneo(V, Cliente, Ora, Min, G, M), Lista).

% Tutti i clienti servibili da un dato veicolo in un dato momento
clienti_servibili_da(Veicolo, Ora, Min, G, M, Lista) :-
    findall(C, furgone_idoneo(Veicolo, C, Ora, Min, G, M), Lista).
