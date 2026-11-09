# eVijećnica: pitch u 3 minute (hrvatski)

Izazov 1: **Društvo i javne usluge** (pristup javnim informacijama, transparentnost, pristupačnost).
Okvirno 450 riječi, oko 3 minute govora. Brojke su izmjerene 7. 11. 2026. i provjerljive na http://localhost:8103/feed.

## 0:00–0:30 Problem
Gradsko vijeće odlučuje o tvom autobusu, vrtiću, odvozu smeća i porezu na kavu. A mladi ne prate lokalnu politiku, i to ne zato što ih nije briga, nego zato što je nečitljiva: dnevni red na jednoj stranici, glasovanje u PDF-u, zapisnik tjednima kasnije, sve birokratskim jezikom.
Posljedica se vidi na izborima: drugi krug lokalnih izbora 2025. imao je najmanji odaziv otkako se lokalni izbori održavaju (1993.).
Više od trećine mladih (36,8 %) nije izašlo na prethodne izbore iako su imali pravo glasa, a najčešći razlog je „ništa se ne bi promijenilo”. Lokalnoj samoupravi vjeruje 13,6 % mladih. Autori zaključuju da prevladavaju razlozi povezani s manjkom osnaženosti i informiranosti, a to je upravo ono što eVijećnica mijenja.

I ne samo mladi: na lokalnim izborima 2025. u 20 najvećih gradova nije glasovalo **957.627** od 1.596.312 upisanih birača, šest od deset (izlaznost 40,01 %). Najniža je bila u Kaštelima (29,24 %), Osijeku (33,32 %) i Rijeci (34,82 %): ondje dvoje od troje birača nije izašlo.
<!-- Izvor: DIP, rezultati lokalnih izbora 2025., 1. krug, izbor gradskog vijeća / Gradske skupštine (izbori.hr arhiva, datoteke 557_*.xlsx; skup „Rezultati lokalnih izbora” na data.gov.hr); upisani i glasovali zbrojeni po biračkim mjestima, collect/datagovhr.py. -->
<!-- Izvor: Adamović, Antulić Majcen, Baketa, Đokić, Ilišin, Potočnik: Studija o mladima Hrvatska 2024: mladi u vremenu neizvjesnosti, FES i Institut za društvena istraživanja, 2024. (N = 717, 14–29 godina; samoiskaz za parlamentarne izbore 2020.). DIP ne objavljuje izlaznost po dobi. -->

## 0:30–1:15 Rješenje
**eVijećnica pretvara sjednice gradskih vijeća u objave za društvene mreže**, s oznakom grada i teme: `#Zagreb #promet`, `#SlavonskiBrod #otpad`. Pratiš svoj grad i ono što te zanima, a ne politiku općenito.
Pokažem tri objave iz feeda:
- **Slavonski Brod:** „Svi plaćaju 25 % višu komunalnu naknadu: bod raste na 1 euro.” 12 za, 6 protiv, 1 suzdržan, uz argumente obje strane.
- **Zagreb:** „Bez gradskog novca za preglede djece sportaša: prijedlog odbijen.” Uz slajd „Kako su glasali klubovi” iz službenog poimeničnog glasovanja: tko je bio za, tko protiv, a tko je bio u dvorani i nije glasovao.
- **Rijeka:** „Izvještaj o trošenju gradskog novca u 2025. nije dobio većinu.”
Svaka objava je karusel od 3 do 5 slajdova: što je odlučeno, što to znači za tebe, tko je što rekao, kako se glasovalo, i redak o izvoru.
**Kanali:** Instagram za karusele, a **Reddit** za raspravu: tjedni pregled po gradu u r/croatia (oko 440 tisuća članova), r/hrvatska i r/zagreb, uz dopuštenje moderatora, i vlastiti subreddit s oznakom po gradu. Na Redditu ljudi komentiraju i ispravljaju, a ispod svake objave stoji izvor.

## 1:15–2:15 Kako radi i zašto mu možeš vjerovati
- **Podaci:** službene stranice 31 grada i općine, među njima svih 15 najvećih gradova (Zagreb, Split, Rijeka, Osijek, Zadar, Velika Gorica, Pula, Slavonski Brod, Karlovac, Varaždin, Šibenik, Dubrovnik, Sisak, Kaštela, Samobor) i manje jedinice od Kastva do Punta: 332 sjednice i 6.461 točka dnevnog reda, od kojih 4.080 s ishodom glasovanja. 17 gradova ima vlastiti skupljač, a 14 jedinica pokriva jedan zajednički skupljač za sustav eSjednice. Zapisnici, poimenično glasovanje i snimke sjednica. Novi grad je jedan skupljač podataka; sve ostalo (odabir, pisanje, slike) radi bez promjena.
- **Odabir bez biranja strana:** pravila su fiksna i javna. Svaka točka s barem jednim glasom protiv ili suzdržanim dobiva svoju objavu, a sve jednoglasno ide u objavu „Ukratko”. Nitko ne bira što je zanimljivo.
- **Pisanje:** AI piše prema strogim pravilima: samo činjenice iz zapisnika, svaki argument pripisan klubu, bez imena privatnih osoba, bez vlastitih procjena.
- **Dvostruka provjera.** AI pisac ne samo da piše nego i uspoređuje brojke sa zapisnikom. Tako smo tijekom izrade uhvatili sjednicu na kojoj su se glasovi pomaknuli za jednu točku (vijeće je promijenilo redoslijed) i 26 šibenskih glasovanja kojima su nedostajali glasovi protiv, među njima dva rebalansa proračuna. U zapisnicima Čakovca tri puta se broj glasova koji izgovori predsjedatelj razlikuje od službenog zaključka; u jednom zaključku zbroj glasova veći je od broja vijećnika (21 od 19), pa taj rezultat ne objavljujemo. Jedan krivo izračunat postotak uhvatili smo pri ljudskoj provjeri. Zato svaka objava prolazi i ljudsku provjeru, a stroj radi ostalo.
- **Rezultat danas:** 1.223 objave iz 24 grada i općine, 4.089 slika spremnih za Instagram (1080×1350) i 1.223 objave pripremljene za Reddit, automatski. Objave zadnjih sjednica pisane su i iz materijala (prijedlog odluke, obrazloženje), pa kažu konkretno što se mijenja (npr. Zagreb: porez na nekretnine od 2027. 8,00 eura po m² umjesto 5,00), a rasprava dolazi i iz snimke sjednice. Uz „Samo bitno” ostaje 888 odluka koje se izravno tiču stanovnika; tko želi, bira svoj grad i teme.

## 2:15–2:45 Zašto baš sada
Zapisnici kasne. Danas, 7. 11. 2026.:
- Krk, 7. sjednica (21. 7.): **109 dana** bez zapisnika.
- Osijek: uz točke za usvajanje zapisnika 5., 6. i 7. sjednice (veljača–svibanj 2026.) zapisnici nisu objavljeni, iako su uz sve ranije sjednice.
- Rijeka, 12. sjednica: 44 dana. Krk, 8. sjednica: 40 dana. Slavonski Brod, 10. sjednica: 29 dana.
A uživo se često ne može ni pratiti: Gradsko vijeće Krka u ožujku 2026. odbilo je prijedlog da se sjednice prenose uživo (2 za, 7 protiv, 1 suzdržan), a Gradsko vijeće Čakovca u prosincu 2025. prijedlog da se sjednice snimaju i prenose videom (4 za, 12 protiv, 2 suzdržana).
eVijećnica objavljuje čim zapisnik izađe, a prototip već prepoznaje govor sa snimke sjednice, pa rezultate može najaviti i prije zapisnika, jasno označene kao neslužbene. Na 9. sjednici Broda svih 11 rezultata koje je predsjedatelj izgovorio s brojem glasova prepoznato je točno do glasa, provjereno prema zapisniku.

## 2:45–3:00 Što tražimo
- Grad ili savjet mladih za **pilot**: jedan Instagram profil po gradu kroz tri mjeseca, i mjerimo doseg među mladima.
- Pristup sustavu za glasovanje i zapisnicima u strojnom obliku, da provjera bude brža.
Hrvatska ima 556 jedinica lokalne samouprave, a put do svih je konkretan:
- **Jedan skupljač već pokriva 14 jedinica:** gradovi i općine na istom sustavu za sjednice (NetCom eSjednice), od Splita, Opatije i Senja do Punta i Viškova; sljedeća jedinica na istom sustavu dodaje se redom u postavkama, uz provjeru njezinih zapisnika.
- **Isti obrasci u cijeloj zemlji:** zapisnici gotovo svugdje pišu „Točka N.” i „N glasova ZA”, pa jedan parser radi za većinu.
- **Dvije razine:** gdje postoje zapisnici, objave s glasovanjem; za ostale, dnevni red i odluke iz službenog glasnika te stranački sastav vijeća iz podataka DIP-a za svih 556 jedinica.

## Napomene za pitanja žirija
- **Neutralnost:** odabir je pravilom, ne urednikom. Tko je kako glasao dolazi iz službenog poimeničnog glasovanja (Zagreb), a ne iz tumačenja. Kad zapisnik ne kaže kako je klub glasovao, objava piše „nepoznato”, ne nagađa.
- **Zašto ne samo ChatGPT:** ChatGPT nema podatke. Vrijednost je u prikupljanju i povezivanju zapisnika, glasovanja i snimki za svaki grad, i u pravilima koja sprječavaju izmišljanje.
- **Točnost:** brojke glasova prepisane su iz zapisnika. Sažetak je strojni i svaka objava to kaže; službeni dokumenti imaju prednost.
- **Reddit, kako točno:** objave priprema sustav, a objavljuje ih osoba, bez bota. Reddit od studenog 2025. traži odobrenje za automatizirani pristup i oznaku „App” na bot računima, a novi račun koji brzo objavljuje slične poveznice lako završi kao spam. Zato prvo pitamo moderatore smijemo li objavljivati tjedni pregled i pod kojom oznakom („Politika”), a prvi komentar ispod objave kaže da je tekst strojno pripremljen i ljudski pregledan te poziva na ispravke uz izvor. Brojke članova su iz vanjskih statistika ([GummySearch](https://gummysearch.com/r/croatia/)); pravila subredita treba provjeriti prije prve objave.
- **Što ne radimo (još):** video isječke iz snimki. Transkripti postoje (prepoznavanje govora na računalu s Apple čipom, oko 30 puta brže od stvarnog vremena), pa su isječci sljedeći korak.
- **Mladi i izbori, odakle brojke:** Studija o mladima Hrvatska 2024 (FES i Institut za društvena istraživanja, N = 717, 14–29 god.): 36,8 % nije izašlo na prethodne (parlamentarne) izbore iako su imali pravo glasa; razlozi: „ništa se ne bi promijenilo” 26,5 %, nije bilo stranke za koju bi glasali 14,6 %, nezainteresiranost 12 %, nedovoljna informiranost 9 %. Povjerenje u lokalnu samoupravu 13,6 %. Samoiskaz, pa je stvarna apstinencija vjerojatno veća; službene izlaznosti po dobi nema. ([PDF](https://collections.fes.de/publikationen/download/pdf/1572127))
- **Nisu glasovali, 20 najvećih gradova (lokalni izbori 2025., DIP):** Zagreb 383.005 (izlaznost 42,65 %), Split 87.968 (37,30 %), Rijeka 63.583 (34,82 %), Osijek 57.068 (33,32 %), Zadar 38.959 (37,12 %), Velika Gorica 34.789 (37,12 %), Slavonski Brod 31.012 (35,81 %), Pula 27.855 (40,85 %), Karlovac 25.928 (40,74 %), Kaštela 25.058 (29,24 %), Šibenik 24.178 (37,38 %), Varaždin 23.115 (39,27 %), Bjelovar 19.991 (36,57 %), Dubrovnik 19.451 (47,01 %), Sisak 18.035 (50,53 %), Vinkovci 17.445 (37,81 %), Samobor 16.532 (50,11 %), Koprivnica 15.783 (37,92 %), Solin 14.010 (36,00 %), Čakovec 13.862 (40,68 %); ukupno 957.627 od 1.596.312 (40,01 %). Izlaznosti po dobi DIP ne objavljuje.
- **Izvori konteksta:** odaziv na lokalnim izborima 2025. ([N1/Hina](https://n1info.rs/region/superizborna-godina-u-hrvatskoj-zavrsena-malom-izlaznoscu/)); niska politička participacija mladih ([EU Youth Wiki, Hrvatska](https://national-policies.eacea.ec.europa.eu/youthwiki/chapters/croatia/5-participation)).
