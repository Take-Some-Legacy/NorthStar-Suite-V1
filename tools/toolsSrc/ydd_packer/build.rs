#[cfg(target_os = "windows")]
fn main() {
    let version = env!("CARGO_PKG_VERSION");
    let icon_path = "../icons/northstar-ydd-packer.ico";

    println!("cargo:rerun-if-changed={icon_path}");

    let mut resource = winres::WindowsResource::new();
    resource.set_icon(icon_path);
    resource.set("CompanyName", "Take Some");
    resource.set("FileDescription", "North Star YDD NEF8 drawable dictionary importer");
    resource.set("FileVersion", version);
    resource.set("InternalName", "northstar-ydd-packer");
    resource.set("LegalCopyright", "Copyright (c) Take Some");
    resource.set("OriginalFilename", "northstar-ydd-packer.exe");
    resource.set("ProductName", "North Star Engine Tools");
    resource.set("ProductVersion", version);
    resource.set_language(0x0409);

    if let Err(err) = resource.compile() {
        panic!("failed to compile Windows resources for northstar-ydd-packer: {err}");
    }
}

#[cfg(not(target_os = "windows"))]
fn main() {}
