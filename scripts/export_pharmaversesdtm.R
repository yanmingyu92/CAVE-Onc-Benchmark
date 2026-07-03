# export_pharmaversesdtm.R — Export pharmaversesdtm datasets to SAS V5 XPT
# Usage: Rscript scripts/export_pharmaversesdtm.R [recist|onco]
# Determinism: haven::write_xpt embeds timestamps. This script replaces
# them with a fixed value so re-runs produce byte-identical output.

args <- commandArgs(trailingOnly = TRUE)
corpus <- if (length(args) > 0) args[1] else "recist"
stopifnot(corpus %in% c("recist", "onco"))

library(pharmaversesdtm)
library(haven)

COLON <- charToRaw(":")[[1]]
MONTHS <- list(
  charToRaw("JAN"), charToRaw("FEB"), charToRaw("MAR"),
  charToRaw("APR"), charToRaw("MAY"), charToRaw("JUN"),
  charToRaw("JUL"), charToRaw("AUG"), charToRaw("SEP"),
  charToRaw("OCT"), charToRaw("NOV"), charToRaw("DEC")
)
FIXED <- as.raw(c(
  0x30, 0x31, 0x4A, 0x41, 0x4E, 0x30, 0x30, 0x3A,
  0x30, 0x30, 0x3A, 0x30, 0x30, 0x3A, 0x30, 0x30
))

stamp_all_timestamps <- function(path) {
  b <- readBin(path, "raw", file.info(path)$size)
  n <- length(b)
  i <- 1L
  while (i + 15L <= n) {
    chunk <- b[i:(i + 15L)]
    # SAS V5 timestamp: DDMMMYY:HH:MM:SS
    # Positions (1-indexed): 8=colon, 11=colon, 14=colon
    if (chunk[8] == COLON && chunk[11] == COLON && chunk[14] == COLON) {
      mon <- chunk[3:5]
      for (m in MONTHS) {
        if (all(mon == m)) {
          b[i:(i + 15L)] <- FIXED
          break
        }
      }
    }
    i <- i + 1L
  }
  writeBin(b, path)
}

write_sorted_xpt <- function(df, outpath, sort_cols) {
  df <- df[do.call(order, df[, sort_cols, drop = FALSE]), ]
  haven::write_xpt(df, path = outpath, version = 5)
  stamp_all_timestamps(outpath)
}

out_dir <- if (corpus == "recist") "data/pharmaversesdtm_recist" else "data/pharmaversesdtm_onco"
seq_col <- list(tu = "TUSEQ", tr = "TRSEQ", rs = "RSSEQ")
domains <- c("tu", "tr", "rs")
if (!dir.exists(out_dir)) dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

for (d in domains) {
  ds_name <- paste0(d, "_onco", if (corpus == "recist") "_recist" else "")
  e <- new.env()
  data(list = ds_name, envir = e)
  write_sorted_xpt(get(ds_name, envir = e),
                   file.path(out_dir, paste0(d, ".xpt")),
                   c("USUBJID", "VISITNUM", seq_col[[d]]))
}

cat("Exported", corpus, "corpus to", out_dir, "\n")
