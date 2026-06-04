#[cfg(target_os = "windows")]
fn main() {
    let version = env!("CARGO_PKG_VERSION");
    let icon_path = "../icons/northstar-ytd-packer.ico";

    println!("cargo:rerun-if-changed={icon_path}");

    let mut resource = winres::WindowsResource::new();
    resource.set_icon(icon_path);
    resource.set("CompanyName", "Take Some");
    resource.set("FileDescription", "North Star YTD Packer");
    resource.set("FileVersion", version);
    resource.set("InternalName", "northstar-ytd-packer");
    resource.set("LegalCopyright", "Copyright (c) Take Some");
    resource.set("OriginalFilename", "northstar-ytd-packer.exe");
    resource.set("ProductName", "North Star Engine Tools");
    resource.set("ProductVersion", version);
    resource.set_language(0x0409);

    if let Err(err) = resource.compile() {
        panic!("failed to compile Windows resources for northstar-ytd-packer: {err}");
    }
}

#[cfg(not(target_os = "windows"))]
fn main() {}
