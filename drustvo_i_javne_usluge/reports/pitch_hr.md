# Vijećnica: pitch u 3 minute (hrvatski)

Okvirno 420 riječi, oko 3 minute govora. Brojke su izmjerene 6. 11. 2026. i provjerljive su na http://localhost:8103.

## 0:00–0:30 Problem
Gradsko vijeće odlučuje o novcu svih nas, ali je trag tih odluka razbacan: dnevni red na jednoj stranici, glasovanje u PDF-u po točki, snimka na YouTubeu ili u MP3-u, a zapisnik stiže tjednima kasnije.
Slavonski Brod je 10. sjednicu održao 9. listopada. Danas je 6. studenoga, **28 dana kasnije**, a zapisnika još nema.
Zagrebački zapisnik 14. sjednice izrađen je kao PDF **13 dana** nakon sjednice (datum izrade PDF-a, ne datum objave), s oznakom „neverificirani”.

## 0:30–1:15 Rješenje
Vijećnica spaja službene otvorene podatke dvaju gradova sa strojnim transkriptom snimke. Svaka tvrdnja iz transkribirane snimke ima poveznicu na točnu sekundu; zasad je transkribirana 1 od 33 zagrebačke snimke i 4 od 12 brodskih, a ostalo vodi na službeni dokument ili cijelu snimku.
- **Građanin** upiše „tramvaj” i dobije točke dnevnog reda, pitanja vijećnika i trenutke u snimci.
- **Novinar** vidi kako je glasao svaki klub. Sada razlikujemo „odsutan” od „bio na sjednici, nije glasovao”, jer to nije isto: od 4.977 glasova koje službeni PDF bilježi kao „odsutan”, 3.105 pripada zastupnicima koji su toga dana bili na sjednici, a još 3.592 puta prisutni zastupnik u PDF-u ima redak bez ikakve oznake. Ukupno 6.697 puta zastupnik je bio u dvorani, a nije glasovao.
- **Službenik** dobije nacrt zapisnika u službenom obliku.

Sve je dostupno i kao MCP poslužitelj, pa ga svaki AI asistent može pitati o radu vijeća.

## 1:15–2:15 Dokaz: manje administracije
- **Zagreb, 14. sjednica:** stroj sastavi nacrt zapisnika za svih 32 točke za **0,01 sekunde**, iz dnevnog reda, poimeničnog glasovanja i govornika prepoznatih u snimci. Službeni zapisnik izašao je 13 dana nakon sjednice. Prepoznavanje govora za tu sjednicu jednokratno traje oko sat vremena na računalu s Apple čipom.
- **Usporedba nacrta sa službenim zapisnikom:** pronađeno je 15 od 22 govornika, uz preciznost 100 %, i 18 od 42 javljanja. Vrsta akta je točna 21 od 21 puta. Brojke glasova u nacrtu prepisane su iz poimeničnog glasovanja, pa se poklapaju po konstrukciji; to nije mjerenje.
- **Slavonski Brod, 10. sjednica, četiri tjedna prije zapisnika:** iz riječi predsjedatelja („konstatiram da smo s 12 glasova za, 7 protiv i 1 suzdržanim usvojili…”) izdvojili smo rezultate glasovanja za **14 od 17 točaka** o kojima se glasuje (aktualni sat nema glasovanja); za 13 je izgovoren i broj glasova. Prepoznali smo i **17 vijećnika** koji su govorili, svakoga s poveznicom na trenutak snimke. Svi su ti rezultati jasno označeni kao „iz snimke, neslužbeno”.
- **Koliko tome vjerovati, izmjereno:** na 9. sjednici Broda, za koju gotovo doslovan zapisnik postoji, **8 od 8** rezultata s izgovorenim brojem točno je do glasa, a **68 %** riječi strojnog zapisa slaže se sa zapisnikom (WER 0,32 na 10.984 riječi, na 86 od 99 odlomaka koje zapisnik prenosi; zapisnik je uređen tekst, pa je to donja granica točnosti).

## 2:15–2:45 Otvoreni podaci
Izvoz je spreman za data.gov.hr (CKAN / Frictionless Data Package), s licencom po datoteci: CC BY 4.0 za ono što smo izveli (transkripti, govornici, obećanja, struktura), a za doslovno preneseni službeni tekst uvjeti izvora i ponovna uporaba prema Zakonu o pravu na pristup informacijama. Uz izvoz idu sha256 i vrijeme dohvata svake izvorne datoteke. Ništa još nije objavljeno.

## 2:45–3:00 Što tražimo
Partnera u gradskoj upravi koji će nam dati pristup:
- sustavu za glasovanje, jer zapisnik prijava za riječ rješava govornike koje predsjedatelj ne prozove imenom;
- kvalitetnijem zvuku sa snimki sjednica.

Model se može proširiti na svaki grad koji objavljuje snimke.

## Napomena za pitanja žirija
- **Obećanja:** obećanja iz aktualnog sata s prošlim rokom označena su kao „rok prošao, ispunjenje neprovjereno”. Pomoćnik „provjeri ispunjenje” traži temu na kasnijim sjednicama i označi „spominje se kasnije” s poveznicama (26 od 57 obećanja), ali to nije tvrdnja da je obećanje ispunjeno. Izdvojena su pravilima iz službenih fonograma.
- **Brzina prepoznavanja govora:** na ovom poslužitelju (i5, bez grafičke kartice) radi oko 0,9 puta brzinom stvarnog vremena. Za 244 minute zvuka trebalo je 287 minuta. Dugačke zagrebačke sjednice zato se obrađuju na računalu s Apple čipom, oko 24 puta brže od stvarnog vremena.
- **Transkript i govornici su strojni:** službeni dokumenti uvijek imaju prednost.
