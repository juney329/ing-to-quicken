## ING (Germany) → Quicken CSV Converter

Convert an ING (Germany) account export (semicolon-separated CSV) into a Quicken-compatible CSV ready for import.

### What this does
- **Parses ING CSV**: Detects the transaction table starting at the header that begins with `Buchung;…` and includes `;Betrag`.
- **Handles encodings**: Tries `utf-8-sig`, `utf-8`, then `latin-1` to tolerate ING exports.
- **Normalizes text**: Transliterates German umlauts (ä→ae, ö→oe, ü→ue, ß→ss), strips non-ASCII, and collapses whitespace (to keep Quicken happy).
- **Converts formats**: Turns German dates `dd.mm.yyyy` into `mm/dd/yyyy` and German amounts (e.g., `-1.770,00`) into signed decimals (`-1770.00`).
- **Builds memos**: Concatenates `Buchungstext` and `Verwendungszweck` into the Quicken `Memo` field.
- **Outputs Quicken CSV**: Writes the 10-column layout Quicken expects with a fixed Account name.

### Requirements
- **Python**: 3.9+ (uses modern type hints and standard library only)
- **Dependencies**: None outside the Python standard library

### Usage
```bash
python3 convert_ing_to_quicken.py ING_Bank_Import.csv output_quicken.csv --default-account "ING Checking"
```

- **input**: Path to your ING export CSV (see “Input format”).
- **output**: Where to write the Quicken-compatible CSV.
- **--default-account**: Account name to place in the Quicken `Account` column. Defaults to `ING Checking`.

Example:
```bash
python3 convert_ing_to_quicken.py ./ING_Bank_Import.csv ./quicken_import.csv --default-account "ING Giro"
```

When done, you should see a message like:
```
Wrote 42 transactions to quicken_import.csv
```

### Input format (ING export)
Export transactions from ING as CSV. The tool looks for the transaction header row that starts with `Buchung;` and contains `;Betrag`.

Minimal example of the data header and a row (semicolon-separated):
```text
Buchung;Wertstellungsdatum;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Währung;Betrag;Währung
02.09.2025;02.09.2025;ING;Entgelt;GIROCARD …;14.115,21;EUR;-1,49;EUR
```

Notes:
- Pending transactions are not included by ING in the CSV (ING provides only posted transactions).
- Header/metadata lines before the table (e.g., `Kontoname;…`) are ignored.

### Output format (Quicken CSV)
The generated file includes the following columns in this exact order:

1. Date
2. Payee
3. FI Payee
4. Amount
5. Debit/Credit
6. Category
7. Account
8. Tag
9. Memo
10. Chknum

Details:
- **Date**: Converted to `mm/dd/yyyy`.
- **Payee**: From `Auftraggeber/Empfänger` (normalized to ASCII).
- **FI Payee**: Left blank.
- **Amount**: Signed decimal; `Debit/Credit` is left blank (Quicken prefers signed amounts).
- **Category**, **Tag**, **Chknum**: Left blank.
- **Account**: Set from `--default-account` (defaults to `ING Checking`).
- **Memo**: `Buchungstext` and `Verwendungszweck` joined with ` | ` (normalized to ASCII).

For Quicken’s official column expectations and import steps, see `QUicken import rules.md` in this repository.

### Importing into Quicken
1. Open Quicken.
2. File → File Import → Transactions from .CSV File.
3. Select the generated CSV.
4. If prompted about accounts, choose an existing account or create a new one matching the `Account` name used.

### Troubleshooting
- **"Could not locate transaction header row starting with 'Buchung;'"**
  - Ensure your file is the ING CSV export and uses semicolons (`;`). The header line must begin with `Buchung;` and contain `;Betrag`.
- **"Unparseable amount" warnings or missing rows**
  - Check that amounts are in German notation (thousands `.` and decimal `,`). The script strips thousands separators and converts decimals.
- **No transactions parsed**
  - Verify the export covers the expected date range and contains posted transactions.
- **Garbled umlauts or special characters**
  - The script tries `utf-8-sig`, `utf-8`, then `latin-1`. If issues persist, re-export the CSV and avoid editing it in tools that may alter encoding.

### Notes and limitations
- Transfers are not auto-detected or linked; Quicken may treat them as separate cash flows.
- Duplicate imports are not de-duplicated by the script; re-importing the same CSV in Quicken may create duplicates.
- The account name is not read from the file; it’s set via `--default-account`.

### Repository contents
- `convert_ing_to_quicken.py`: Conversion script and CLI.
- `QUicken import rules.md`: Quicken CSV format expectations and import guidance.
- `ING_Bank_Import.csv`: Example ING export (sample data) for testing.


