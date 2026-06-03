fn main() {
    #[cfg(windows)]
    {
        let mut res = winres::WindowsResource::new();
        res.set("FileDescription", "North Star NEFTD NEF8 font dictionary tool");
        res.set("ProductName", "North Star Engine Tools");
        let _ = res.compile();
    }
}
