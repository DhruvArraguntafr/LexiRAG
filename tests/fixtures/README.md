# Verified statutory excerpt

`ecommerce_rules_verified.txt` contains Rules 4(5) and 4(9), checked directly against original scanned PDF page 4 (printed page 82) of the user's uploaded E-Commerce Rules, SHA-256 `54fed9f2b119f487c66af671f338e7962f9cf22b55e1e8ba3456219e3394872a`. The literal forty-/eight line wrap is retained. The parent Rule 4 heading is supplied for this excerpt fixture; the actual original heading is on PDF page 3. These test excerpts are not fabricated teaching law.

`consumer_rights_verified.txt` is an excerpt fixture, not the complete Act and not invented teaching law. The six clauses were checked against the user's uploaded `CP Act 2019_1732700731.pdf`, SHA-256 `0ae7f82ab5b77d50087cd4cd2dd2dbc12755c0bdb31371fdefd042b020d50756`, original PDF pages 3–4. The parent Definitions heading is on PDF page 2. Whitespace is normalized and a readable `Section 2 Definitions` heading is supplied as fixture metadata. The original PDF remains in the private library.

Official reference: [Department of Consumer Affairs — Consumer Protection Acts](https://consumeraffairs.gov.in/pages/consumer-protection-acts). An [India Code copy](https://www.indiacode.nic.in/bitstream/123456789/15276/1/210422.pdf) is also available; the online PDF fetch timed out during this run, so verification used the actual uploaded original.

Tests render the excerpt into temporary PDFs, including a page break between items (ii) and (iii). Deterministic unit generators only test evidence plumbing; separate live checks use the actual Act, real local model weights and Gemini.
