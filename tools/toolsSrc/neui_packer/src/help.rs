use std::io;

pub fn print_help() {
    println!("North Star NEUI Packer / XMLcentral tool");
    println!();
    println!("Canonical authoring source: *.neui.xml (XMLcentral, XML-first, arbitrary fields allowed).");
    println!("Runtime asset: *.neui is NEF8/ListFile with deflate-compressed XML body.");
    println!("Legacy .neui.import.json manifests are not supported.");
    println!();
    println!("Usage:");
    println!("  northstar-neui-packer compile --root <repo> --input assets/ui/editor/main.neui.xml --output assets/ui/editor/main.neui");
    println!("  northstar-neui-packer compile --root <repo> --all [--check]");
    println!("  northstar-neui-packer inspect --input assets/ui/editor/main.neui");
    println!("  northstar-neui-packer dump-xmlcentral --input assets/ui/editor/main.neui [--output main.neui.xml]");
    println!("  northstar-neui-packer validate --root <repo> --all");
    println!("  northstar-neui-packer manifest --input assets/ui/editor/main.neui");
    println!("  northstar-neui-packer dump-compiled-document --input assets/ui/editor/main.neui");
    println!("  northstar-neui-packer dump-binding-plan --input assets/ui/editor/main.neui");
    println!("  northstar-neui-packer dump-dependencies --input assets/ui/editor/main.neui");
}

pub fn wait_for_enter() {
    println!();
    println!("This tool works through arguments. Press Enter to close...");
    let mut line = String::new();
    let _ = io::stdin().read_line(&mut line);
}
