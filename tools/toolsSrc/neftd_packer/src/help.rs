use std::io::{self, IsTerminal};

pub fn print_help() {
    println!(r#"northstar-neftd-packer

Purpose:
  Create, pack, inspect, list, validate and extract .neftd font dictionaries.
  .neftd = North Star Font Dictionary. It is a NEF8 ListFile asset.
  YFT remains free for a future fragment-like format.

Commands:
  create   --input font.ttf --output fonts/ui.neftd [--entry regular]
  pack     --input fonts/source_dir --output fonts/ui.neftd
  inspect  --input fonts/ui.neftd
  list     --input fonts/ui.neftd
  validate --input fonts/ui.neftd
  extract  --input fonts/ui.neftd --entry regular --out-dir out --overwrite

Source formats:
  TTF, OTF, WOFF, WOFF2, TTC.

Notes:
  This tool stores validated font source bytes and metadata in a native font dictionary.
  It does not shape text, rasterize glyphs, or depend on a renderer/text backend.
"#);
}

pub fn wait_for_enter() {
    if io::stdin().is_terminal() {
        println!("Press Enter to close...");
        let mut line = String::new();
        let _ = io::stdin().read_line(&mut line);
    }
}
