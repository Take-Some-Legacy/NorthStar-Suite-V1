use std::io::{self, IsTerminal};

pub fn print_help() {
    println!(r#"northstar-nepak-packer

Purpose:
  Pack, extract, inspect and validate .nepak VFS packages.
  .nepak is a generic opaque-byte container. It can store any file type,
  including another nested .nepak. Entries are bytes + paths, not typed assets.

Commands:
  pack     --input <file-or-directory> --output package.nepak [--no-compress]
  extract  --input package.nepak --output <directory> [--path package/path] [--overwrite]
  inspect  --input package.nepak
  validate --input package.nepak

Options:
  --input, -i       Input file, input directory, or package depending on command.
  --output, -o      Output .nepak or extraction directory.
  --path, --entry   Extract only one package path.
  --overwrite       Allow extract to overwrite existing files.
  --no-compress     Store payloads raw instead of deflate-compressed.

Examples:
  northstar-nepak-packer pack -i assets/runtime -o builds/runtime.nepak
  northstar-nepak-packer pack -i builds/runtime.nepak -o builds/wrapped.nepak
  northstar-nepak-packer inspect -i builds/runtime.nepak
  northstar-nepak-packer validate -i builds/runtime.nepak
  northstar-nepak-packer extract -i builds/runtime.nepak -o .takesome/extract/nepak --overwrite
"#);
    println!();
    println!("Common commands:");
    println!("  pack/build/compile/create/import     Build a runtime asset where supported.");
    println!("  inspect | validate | doctor          Inspect or validate an existing runtime asset.");
    println!("  accepted-inputs                      Print accepted input/output contract.");
    println!("  version                              Print tool version.");
    println!();
    println!("Accepted input files: directory trees and opaque loose files for pack; *.nepak for inspect/validate/extract");
    println!("Produced output files: *.nepak VFS container; extracted directory trees");
    println!("Output modes: default production output; add --debug or --verbose for debug diagnostics.");
}
pub fn wait_for_enter() {
    if io::stdin().is_terminal() {
        println!("Press Enter to close...");
        let mut line = String::new();
        let _ = io::stdin().read_line(&mut line);
    }
}
