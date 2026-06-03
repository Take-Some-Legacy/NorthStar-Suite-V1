fn main() {
    #[cfg(windows)]
    {
        let mut res = winres::WindowsResource::new();
        res.set("FileDescription", "North Star NEMAT material library tool");
        res.set("ProductName", "North Star Engine Tools");
        res.set("OriginalFilename", "northstar-nemat-packer.exe");
        let _ = res.compile();
    }
}
