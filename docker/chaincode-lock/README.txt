Lock file of the live chaincode image (yarn.lock or package-lock.json), recorded with one
read-only VM command during step 3. Empty until then; scripts/qfp.py build refuses a main-run
build without it.
