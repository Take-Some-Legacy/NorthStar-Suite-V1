#[path = "../../shared/northstar_build/windows_file_info.rs"]
mod windows_file_info;

fn main() {
    windows_file_info::compile(windows_file_info::ToolFileInfo {
        internal_name: "northstar-nepak-packer",
        original_filename: "northstar-nepak-packer.exe",
        file_description: "North Star NEPAK VFS package tool",
        icon_path: Some("../icons/northstar-nepak-packer.ico"),
    });
}
