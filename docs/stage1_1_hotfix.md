# Stage 1.1 hotfix - Windows 10 WGC compatibility

Version: 0.2.2

The first WGC implementation explicitly passed `draw_border=False` and other
optional Graphics Capture settings. Some Windows 10 builds do not support
toggling these capabilities and reject capture startup.

The compatibility defaults are now:

```yaml
cursor_capture: null
draw_border: null
```

`secondary_window`, `minimum_update_interval` and `dirty_region` are also left
unchanged (`None`) internally. Recorder frame-rate limiting is performed in the
Python callback instead of requesting the optional native WGC update-interval
feature.
