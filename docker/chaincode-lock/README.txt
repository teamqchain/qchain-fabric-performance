The live chaincode image (qchain-pqc/ccaas-qchain:2.0 on the live host), read on 16 Nov 2026 with one read-only command:
  ENTRYPOINT ["/bin/sh","-c","exec node_modules/.bin/fabric-chaincode-node server --chaincode-address=$CHAINCODE_SERVER_ADDRESS --chaincode-id=$CHAINCODE_ID"]
  WORKDIR /usr/src/app, USER node (uid 1000), NODE_VERSION 18.20.8, YARN_VERSION 1.22.22, CHAINCODE_SERVER_ADDRESS 0.0.0.0:9998
  installed with npm (package-lock.json present); its full tree is live-npm-ls.txt (`npm ls --all`).
The study's image (LOCK=live) installs the verbatim package.json with npm, then the versions in pins.txt
(the two packages whose newer patch releases npm would otherwise pick), and the build fails unless its
`npm ls --all` equals live-npm-ls.txt.
