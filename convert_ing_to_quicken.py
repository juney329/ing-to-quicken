#!/usr/bin/env python3
import argparse
import csv
import sys
import unicodedata
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Convert an ING (Germany) CSV export to a Quicken-compatible CSV. "
			"Usage: convert_ing_to_quicken.py input.csv output.csv"
		)
	)
	parser.add_argument("input", type=Path, help="Path to ING_Bank_export.csv")
	parser.add_argument("output", type=Path, help="Path to write Quicken CSV output")
	parser.add_argument(
		"--default-account",
		type=str,
		default="ING Checking",
		help=(
			"Account name to populate in the Quicken CSV. "
			"Defaults to 'ING Checking'."
		),
	)
	return parser.parse_args()


def try_read_text(path: Path) -> list[str]:
	"""Read file lines trying utf-8-sig then latin-1 to tolerate export encodings."""
	for encoding in ("utf-8-sig", "utf-8", "latin-1"):
		try:
			with path.open("r", encoding=encoding, newline="") as fp:
				return fp.read().splitlines()
		except UnicodeDecodeError:
			continue
	print(f"Error: could not decode file {path} with utf-8 or latin-1", file=sys.stderr)
	sys.exit(1)


def normalize_to_ascii(text: str) -> str:
	"""Transliterate German umlauts and strip remaining non-ASCII characters.

	- ä->ae, ö->oe, ü->ue, ß->ss, and uppercase equivalents
	- NFKD normalize then ASCII-encode with ignore
	"""
	if not text:
		return ""
	replacements = {
		"Ä": "Ae",
		"Ö": "Oe",
		"Ü": "Ue",
		"ä": "ae",
		"ö": "oe",
		"ü": "ue",
		"ß": "ss",
	}
	for src, dst in replacements.items():
		text = text.replace(src, dst)
	# Decompose accents and drop remaining non-ascii
	text = unicodedata.normalize("NFKD", text)
	text = text.encode("ascii", "ignore").decode("ascii")
	# Collapse weird whitespace
	return " ".join(text.split())


def extract_account_name(lines: list[str], default_account: str) -> str:
	"""Extract account name from a header line like 'Kontoname;Girokonto Future'"""
	for line in lines[:20]:
		parts = line.split(";")
		if len(parts) >= 2 and parts[0].strip().lower().startswith("kontoname"):
			name = parts[1].strip().rstrip(",")
			return name if name else default_account
	return default_account


def find_data_start_index(lines: list[str]) -> int:
	"""Find the index of the header row that starts the transaction table."""
	for idx, line in enumerate(lines):
		header = line.strip()
		# Match the transaction header without relying on special characters like Umlauts
		# Example header contains: 'Buchung;...;Betrag;...'
		if header.startswith("Buchung;") and ";Betrag" in header:
			return idx + 1
	return -1


def parse_german_amount_to_float(text: str) -> float:
	"""Convert amounts like '-1.770,00' or '250,00' to float with '.' decimal."""
	if text is None:
		return 0.0
	clean = text.strip()
	# Some exports may carry trailing commas due to mixed separators; trim extraneous chars
	# Keep only digits, sign, separators
	allowed = set("-+0123456789.,")
	clean = "".join(ch for ch in clean if ch in allowed)
	# Remove thousands separator '.' then replace decimal ',' with '.'
	clean = clean.replace(".", "").replace(",", ".")
	if clean in ("", "+", "-"):
		return 0.0
	try:
		return float(clean)
	except ValueError:
		raise ValueError(f"Unparseable amount: {text!r} -> {clean!r}")


def convert_date_ddmmyyyy_to_mmddyyyy(text: str) -> str:
	"""Convert '14.08.2025' to '08/14/2025' as required by Quicken."""
	text = text.strip()
	for fmt in ("%d.%m.%Y", "%d.%m.%y"):
		try:
			dt = datetime.strptime(text, fmt)
			return dt.strftime("%m/%d/%Y")
		except ValueError:
			continue
	# If parsing fails, leave as-is; Quicken will likely reject, but we preserve data
	return text


def iter_transactions(lines: list[str]) -> list[dict[str, str]]:
	"""Yield parsed transactions from ING CSV-like lines.

	Expected columns (semicolon-separated):
	0 Buchung (date), 1 Wertstellungsdatum, 2 Auftraggeber/Empfaenger,
	3 Buchungstext, 4 Verwendungszweck, 5 Saldo, 6 Waehrung, 7 Betrag, 8 Waehrung
	"""
	start = find_data_start_index(lines)
	if start == -1:
		raise RuntimeError("Could not locate transaction header row starting with 'Buchung;' in input file")

	transactions: list[dict[str, str]] = []
	for raw in lines[start:]:
		line = raw.strip()
		if not line:
			continue
		# Some trailing metadata lines might not contain any semicolons
		if ";" not in line:
			continue
		cols = line.split(";")
		# Require at least 8 columns up to Betrag
		if len(cols) < 8:
			continue

		booking_date = cols[0].strip()
		payee = cols[2].strip() if len(cols) > 2 else ""
		buchungstext = cols[3].strip() if len(cols) > 3 else ""
		verwendungszweck = cols[4].strip() if len(cols) > 4 else ""
		amount_text = cols[7].strip() if len(cols) > 7 else ""

		# Skip if this is the header repeated or malformed
		if booking_date.lower().startswith("buchung"):
			continue

		try:
			amount = parse_german_amount_to_float(amount_text)
		except ValueError:
			# If amount can't be parsed, skip row but keep processing
			continue

		# Normalize text fields to ASCII (Quicken may choke on umlauts)
		payee_ascii = normalize_to_ascii(payee)
		buchungstext_ascii = normalize_to_ascii(buchungstext)
		verwendungszweck_ascii = normalize_to_ascii(verwendungszweck)

		memo_parts: list[str] = []
		if buchungstext_ascii:
			memo_parts.append(buchungstext_ascii)
		if verwendungszweck_ascii and verwendungszweck_ascii != buchungstext_ascii:
			memo_parts.append(verwendungszweck_ascii)
		memo = " | ".join(memo_parts)

		transactions.append(
			{
				"date": convert_date_ddmmyyyy_to_mmddyyyy(booking_date),
				"payee": payee_ascii,
				"fi_payee": "",
				"amount": f"{amount:.2f}",
				"memo": memo,
			}
		)

	return transactions


def write_quicken_csv(path: Path, account_name: str, transactions: list[dict[str, str]]) -> None:
	"""Write rows in Quicken's required column order.

	Columns: Date, Payee, FI Payee, Amount, Debit/Credit, Category, Account, Tag, Memo, Chknum
	Only Date, Payee, Amount, Account are mandatory to be non-empty, but all positions must exist.
	"""
	with path.open("w", encoding="utf-8", newline="") as fp:
		writer = csv.writer(fp)
		writer.writerow([
			"Date",
			"Payee",
			"FI Payee",
			"Amount",
			"Debit/Credit",
			"Category",
			"Account",
			"Tag",
			"Memo",
			"Chknum",
		])
		for tx in transactions:
			writer.writerow(
				[
					tx["date"],
					tx["payee"],
					tx["fi_payee"],
					tx["amount"],
					"",  # Debit/Credit blank (use signed amount)
					"",  # Category blank
					account_name,
					"",  # Tag blank
					tx["memo"],
					"",  # Chknum blank
				]
			)


def main() -> None:
	args = parse_args()
	lines = try_read_text(args.input)
	# Always use the provided default account name (user wants fixed 'ING Checking')
	account_name = args.default_account
	transactions = iter_transactions(lines)
	if not transactions:
		print("Warning: no transactions parsed. Check the input file format.", file=sys.stderr)
	write_quicken_csv(args.output, account_name, transactions)
	print(f"Wrote {len(transactions)} transactions to {args.output}")


if __name__ == "__main__":
	main()


