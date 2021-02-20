Per utilizzare il file clickare sul tasto verde in alto a destra "Code" quindi scegliere l'opzione "download zip". Una volta scaricato estrarre il file "RendicontoDiCassa.xlsm" in una cartella del computer. Aprendo il file excel in alto a sinistra apparirà una striscia "VISUALIZZAZIONE PROTETTA", clickate sul tasto "Abilita modifica".<br/>
# RendicontoCassaETS
Questo file di excel permette di compilare un rendiconto delle spese di un ETS classificandole con le voci definite dall'agenzia delle entrate.<br/>
Nel foglio "<b>Cassa_AAAA</b>", dove AAAA è l'anno di riferimento, vengono registrati i movimenti da rendicontare.
  Clickando su una casella della colonna "Voce" apparirà una <b>tendina con le voci selezionabili</b>. Le voci che terminano con degli asterischi non sono selezionabili.
Nel definire i movimenti nel foglio di cassa è possibile specificare se è relativo ad un movimento di cassa o di conto corrente. I tipi di questa classificazione è definita nel foglio "Rapporti" permettendo, ad esempio, di avere più conti correnti.<br/>
La <b>colonna "Raggruppamento"</b> permette di catalogare un movimento secondo le categorie definite nel foglio "Raggruppamenti". Nella colonna "Subtotale" vengono sommati gli importi delle righe successive con lo stesso raggruppamento. Questo permette, ad esempio, di raggruppare tutte le spese effettuate da un volontario per una particolare missione.<br/>
In alto a destra del foglio "Cassa_AAAA" c'è il tasto "<b>Calcola bilancio annuale</a>" che crea il foglio "Bilancio_AAAA" seguendo lo schema ministeriale totalizzando le voci.<br/> Nel caso che gli importi di una stessa voce non abbiano lo stesso segno viene segnalato un errore e apparirà la totalizzazione con valore -1.<br/>
Il foglio "VociRendiconto" contiene le voci utilizzate per la rendicontazione nel foglio "Cassa". Tali movimenti vengono poi totalizzati nel foglio "Bilancio".<br/>
Le voci sono inizialmente quelle specificate del modello D nell'allegato 1 del Decreto 5 marzo 2020 pubblicato sulla Gazzetta Ufficiale 18 aprile 2020, n. 102.
Solo le voci di terzo livello (quelle contenenti due punti nel "codice" es. U.A.2 - Servizi) o di livelli inferiori sono utilizzabili nel foglio di cassa.
Per meglio specificare l'ambito delle voci si possono aggiungere nuove voci di terzo livello (o livelli ancora inferiori). Es. U.A.2.1 - Servizio A.
Nel foglio "Bilancio" solo le voci del modello D sono totalizzate (raggruppando le voci di livello inferiore).<br/>
Le voci che hanno il codice che inizia per U (uscite) e per E (entrate) sono quelle relative al rendiconto del modello D. Le voci che hanno il codice che inizia con Z sono voci 'strumentali' (saldi iniziali/finali, movimenti di giroconto, totali).<br/>
Il numero della colonna "Id" è un progressivo univoco associato alla voce in modo automatico. L'impostazione manuale di tale codice è sconsigliato.
E' altresì sconsigliato cancellare una voce precedentemente usata.<br/>
Nel caso che ad una voce venga cambiato il significato il procedimento corretto è quello di impostare la colonna "DataFine" nel giorno di tale cambiamento, mentre sulla voce modificata impostando come "DataInizio" il giorno seguente.
Ovviamente tale procedura può essere evitata nel caso che la voce modificata non sia mai stata usata.


