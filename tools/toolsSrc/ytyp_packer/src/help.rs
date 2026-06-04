use std::io;

pub fn print_help() {
    println!("North Star YTYP Packer / generic XML metadata tool");
    println!();
    println!("Canonical authoring source: *.ytyp.xml with arbitrary XML metadata.");
    println!("Runtime asset: *.ytyp is NEF8/ListFile content_kind=3 with deflate-compressed XML body.");
    println!("YTYP is not world-only, material-only or archetype-only. It is a generic metadata cell any domain may consume through explicit refs/contracts.");
    println!();
    println!("Usage:");
    println!("  northstar-ytyp-packer compile --root <repo> --input assets/meta/item.ytyp.xml --output assets/meta/item.ytyp");
    println!("  northstar-ytyp-packer compile --root <repo> --all [--check]");
    println!("  northstar-ytyp-packer inspect --input assets/meta/item.ytyp");
    println!("  northstar-ytyp-packer dump-xml --input assets/meta/item.ytyp [--output item.ytyp.xml]");
    println!("  northstar-ytyp-packer validate --root <repo> --all");
    println!("  northstar-ytyp-packer manifest --input assets/meta/item.ytyp");
    println!("  northstar-ytyp-packer dump-metadata --input assets/meta/item.ytyp");
    println!("  northstar-ytyp-packer dump-dependencies --input assets/meta/item.ytyp");
    println!();
    println!("Common commands:");
    println!("  pack/build/compile/create/import     Build a runtime asset where supported.");
    println!("  inspect | validate | doctor          Inspect or validate an existing runtime asset.");
    println!("  accepted-inputs                      Print accepted input/output contract.");
    println!("  version                              Print tool version.");
    println!();
    println!("Accepted input files: *.ytyp.xml generic metadata XML sources; *.ytyp NEF8 metadata assets for inspect/validate/dump");
    println!("Produced output files: *.ytyp runtime NEF8 metadata dictionary; XML dumps; JSON manifest/metadata/dependency projections");
    println!("Output modes: default production output; add --debug or --verbose for debug diagnostics.");
}
pub fn wait_for_enter() {
    println!();
    println!("This tool works through arguments. Press Enter to close...");
    let mut line = String::new();
    let _ = io::stdin().read_line(&mut line);
}
