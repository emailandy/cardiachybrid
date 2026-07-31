from codegen.emit_contract import main
try:
    main()
except Exception as e:
    import traceback
    traceback.print_exc()
