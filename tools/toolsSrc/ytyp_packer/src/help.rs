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
}

pub fn wait_for_enter() {
    println!();
    println!("This tool works through arguments. Press Enter to close...");
    let mut line = String::new();
    let _ = io::stdin().read_line(&mut line);
}
