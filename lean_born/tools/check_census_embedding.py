#!/usr/bin/env python3
"""Independent binding of the 120 P10 anonymous-initial witnesses.

Uses scaled integer coordinates and its own exact readout/density formulas.
No production carrier, point-search, instrument or interval implementation.
"""
from fractions import Fraction as Q
from pathlib import Path
import argparse
import hashlib
import json
import math

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from born_ladder.reproduction.embedding.census import extract, render, atom_selectors

FIELDS=('raw_by_state','package_by_state','joint_by_state')
MANIFESTS={'original':'66eecc61d9408721013e053d081d7c7f2dcca75ec53ed190b30014106b61bad5',
           'completed':'4f707959dfa3a71e4c2f59ea1856cade357578d5d4d2112cbecd7f38c60c03d6'}
# Exact ordered context commitments are populated below from the retained census.
CONTEXTS=[
  {
    "unit_id": "7556108311046222195906f1c5d983710cbd7a4aeb8f0b21a6753864b1551afe",
    "sha256": "c3a72b4373037619d9272a8809c6d09c47cfbaf33de9d2a91ccf9e82f0df0ee0"
  },
  {
    "unit_id": "194ee69a070dfedac76caa4b0be25621dcef18c318eaaa9d88e86d071b59e7ca",
    "sha256": "d5089ed84d9a04a8e9222f4f8fa60e84df85f2a5174d3f6d9cdee3a9a688a2fe"
  },
  {
    "unit_id": "39548abee2cecc941666a7f11537edb552d0c4e2f55c77a64d9f4f9cf78d8000",
    "sha256": "55d5d02169013588160d29c4c189ef56a3be3ed7b41b486ba085d1af283e4c51"
  },
  {
    "unit_id": "21d00267eb80fd525738ebd504396257aaa60a209095e9e8c04e5af1b9f8759c",
    "sha256": "9ddf53ce4d85b6f1c28617a6658186499c21e29b3a21ef9205bc3cc59bda8775"
  },
  {
    "unit_id": "b681061afb9a535f76aaa0cf741c8bd55c0b649ca2b2ae4f391bed42ba877198",
    "sha256": "aad37453540835137f9fddcbadebabfc9633dc743c99b6213cf23f76609907e0"
  },
  {
    "unit_id": "901fc47dd1da06d9fa22cf28dcf326752f2f5a5e4a73000ec104e9c8b8999700",
    "sha256": "f0a22903522de4ba03a9ba46c28145d25cef00a5f0ad9340407b548bda1f4524"
  },
  {
    "unit_id": "0cf24c427cb116bb1afb41ea4ec09839f2d79515eff12e1ad6a67547522b96d7",
    "sha256": "60f87a6975f4699d68ae4e31abec35ee043ff78749804c03fdaf67aaa103d8b7"
  },
  {
    "unit_id": "1c010c12395d91f6b3d06ed8645b81b36f4fd5a6600232ed1dc946ef40123710",
    "sha256": "261d034272f221fd51e56524bee10bc04c65071ae66b66794df52c5debb765f4"
  },
  {
    "unit_id": "5569fe28e899246f962935d30710307fc830b3547930bc015fe0369acab2ccbc",
    "sha256": "103ef22661b3a35897c3b1b793c929ce3bf7d1363fc9cfc9a2effaf090a07419"
  },
  {
    "unit_id": "a71dc17f4792a7f49521b800ad4651b9041db0164c765a539acd6510128cb7f9",
    "sha256": "81822bdb2b1d7e9987cac8ecb6a6d3d88a376d90edc71ae21c027fd134b615a9"
  },
  {
    "unit_id": "676f5f9d7c93acebd8a941552ed68677c11f4e6928aa96ac9a5a2a311402503d",
    "sha256": "87337d9231f1c69fae0d74d0b7bc893e349b4be0a9ebf31a3e204d486ecae894"
  },
  {
    "unit_id": "e6938a2ae5cfb2adda63913e85003ba528d0630cb283a7115b07ec62f2eb892b",
    "sha256": "7dfe946176e5e46f715f6930ef71839af96d6724a3c0152f16d4b6adb07ac5be"
  },
  {
    "unit_id": "4bc3b00a54f49d341514ce2143ef8ed3f4560b77363fb80664579f3f82ca80fd",
    "sha256": "00ea8f64158cf2292cb9f36aab40f9f137bcdde202bd79f0e294fe49c894db75"
  },
  {
    "unit_id": "b26e50b93b22e436a7f04a505477c4233ad41a5c9070a0bbd57c2494855d43b3",
    "sha256": "2b4f5a9008db2f135706785e29ce9276f29065f923066610356710509345f029"
  },
  {
    "unit_id": "985ecdc9ab3c9b2e3bb927ce847168d7d6b2212cf69220a459737ccfa2c9e66b",
    "sha256": "c082ce307caba2b2e4a391784e3478847ec80e665acacc9108ed4a2198a0a431"
  },
  {
    "unit_id": "bc221b13e5c458d3948531eefa86fa6e2b4887bbce2ab427c0ea927604b99d78",
    "sha256": "f52ccc514ec02d05930cfdb7f142dcf096a9da4e09164f8b902f6a8ee59c2763"
  },
  {
    "unit_id": "566d29658deb4f20621d2579c8b7a47dd2138a767615bb8fab7bbf6a65c9d214",
    "sha256": "e4861fb49954aaee31e5fcc43ca4ddad069769bf4f5b10b69d3bbd9ba9712ad1"
  },
  {
    "unit_id": "4e4e72737fdd6870ab27464e485442c0edd492f3a3c226fa4ffb668664815a2c",
    "sha256": "6394e5b8ad3aeed297135896fab1e339ccb18f4c60b1bff6d3277f3e12d41536"
  },
  {
    "unit_id": "46ebc9687bc2e397dd11cb50a9d730ba3ecf4b3189e3dabe61311ef3a244e5c1",
    "sha256": "4490e69f3e4724140629263624e1162c869d6966de18205ba26f7fd4acf73c0c"
  },
  {
    "unit_id": "196a62f5c955446459aadf6c81dee9d34b51ce8eb952fb3f5b4963e9c3f15f0d",
    "sha256": "227a16f8f359b2cef27c04e16bc882ec23a7c7678caed77ff67d82e8b41a8222"
  },
  {
    "unit_id": "99fa6d5afbf5a0b686ff804be0fc32cc19136a821440d2499e4ac819b29836fd",
    "sha256": "d5353678dbbd0e4f6e04fe93f1ffe88ac40b537433e2501f2f4df85d7a22db8a"
  },
  {
    "unit_id": "670209b5754174b7f8ceca58930b7fc93f5481683f083961fbf3da6d8a49d016",
    "sha256": "1099522bb0c0756e32c7880d2442feddf9199163df5df37c27f8603f0025ce5b"
  },
  {
    "unit_id": "59d5170fe325bb5fbf65484aff672b2aba19ef9f7aa585f3a5e26e31b08e54b3",
    "sha256": "f682265102a4e78e507e807251bfdb89a2005f90aa77c57e66fee06611856e72"
  },
  {
    "unit_id": "404e874a7ef25ce31c03282c747e41791d61b6569a41b548623c1ae249fac665",
    "sha256": "29de5cc3af36ad559ba9b40e1898917d650f6ca092d8f2937f7b46504497499b"
  },
  {
    "unit_id": "5c200c34121e8458747a770565f1fc35e5529d427bf766906c20d6ca2e403563",
    "sha256": "4153371c628f2638103188bc7e4ba0976212d70187d7e3220079936ae909c8e0"
  },
  {
    "unit_id": "d6598130cf639dbfd009cdf1548ef9b66b6cc0aba1f0532fc9298d68c7d2fcc6",
    "sha256": "5f376585e6d535842d006b3669b059771f6d1443a3ed5e477478740bdf33a420"
  },
  {
    "unit_id": "e18fc0c685abbb222fadbf3ff051479caf62b25d86de346da0691609a8bbc063",
    "sha256": "f1208fd97601e9acb08c00540887bf535ecc95338c76416d5ef3a27ab4f1c6ec"
  },
  {
    "unit_id": "c588d06088a759f32d86f0ea825d1c3ec34f7afd75cf2945a12dbebe890d33bc",
    "sha256": "64fc1fdf3bcf18f1e0ef81dfb9e3060301962c357104f11fbb4b9a334b88361f"
  },
  {
    "unit_id": "f33042e159a5264b5acfec3feee7558a89ccac75f6c6e4479284c889bfce52ca",
    "sha256": "6e87bde461c75ac885b454ae2a5c9e9ae16e43056cf28ae4f479a057607a86d5"
  },
  {
    "unit_id": "84a56a0833ce645302ea0ebfc961e44e197a9480f0b7b9876659032c71fb7a54",
    "sha256": "a3739a184ed52a9a98ffa0c1189c18f15e5c181f811f94b437ce62f75b88d686"
  },
  {
    "unit_id": "2106ece67d199a8e5c6a3db223728e6613083b4a4f97309107c3d6b3f210c10f",
    "sha256": "7780fa3b9a4f17f81001c3b37e92486cf1d3d389a76edd162df6971b1c776767"
  },
  {
    "unit_id": "0a382f441db5d1321badb1b622ed5b02405735a18b9879f282cdff89f1b4a433",
    "sha256": "4de9870dff3c373a2435da634a5c586669fcccd60d23baa5ef2ee689dc2d374a"
  },
  {
    "unit_id": "87aad7004b4d5c36792cfa73b9ca3f0e7be5be93c9065bb62e345065351f58ec",
    "sha256": "5a3d22176d97de1523b8a4f9fdcd6a77d4184dc9041df7de35713cb42394aaae"
  },
  {
    "unit_id": "170fd71739dfbe35187c4e6bfade2656a461f68f16b1a1bbe2c6bd78e8ac011b",
    "sha256": "abc24f1e384e31365ef77c1d75a801076b903ca97682f5557407220ae2cdca71"
  },
  {
    "unit_id": "ef6c0dbc705471825933a0a10da54569a5a7893344b11d1bf23f510d4bce98f2",
    "sha256": "fd9388ced3620f4a2bf0381064d174549b595e1a62203b6fa1b90d2ce9cf35cb"
  },
  {
    "unit_id": "35ecae8e009ce4a5c1c405525c687bf1cb087b3bb30109694c3b202d65cc1614",
    "sha256": "731334261d7b945b528950602714b4514dcc9ef1a651733f6c4d3aacd4a1dc94"
  },
  {
    "unit_id": "893fc2ab4919165fd81b19eae0df6c743493770ab0a31983df230b5fb4034559",
    "sha256": "d3e3ca1cfd68d127ee1ab11a100a8782d1282a591145d889ee60383e384f265c"
  },
  {
    "unit_id": "7bee25fb30df6525da2e67a53ab424f5b44036e1b5e7abb20e0a128bf2149da7",
    "sha256": "10918d8e9063b89564169eab56c3e39e2a2d209b791ddd6a6e15f8c6968d0187"
  },
  {
    "unit_id": "fe55361de89037f2346da4cba41bad1bcc2edf1103807da15ac651fa02ff902b",
    "sha256": "72522ff417009478ead9b5fbecf0be3b05c18c697c1dc119170c994b74c9a668"
  },
  {
    "unit_id": "1f1c55fd2705a6ae6b9f0a2a010327fabc61f65a49821afbdcfe308273d8c271",
    "sha256": "6c1942dcc1e49a366a94d7eb5de783b6219fff0ddb53f001130bd9673fcec98d"
  },
  {
    "unit_id": "9f18b311b6583eeb314410313a8bb4b3d9272f9a8bd2360d6217e8556911699f",
    "sha256": "2e429d9502c6ec7846a298074ff7ef6f79b550bc0a7cc156006dc41100c44d06"
  },
  {
    "unit_id": "7452fb6cc670210a42777730949d43df235a597274499d4cd3c7bd3f99663cbf",
    "sha256": "4505c0e9b913b9f9352e255bffa1ca05915124837e8b7969bbe7213190b40dae"
  },
  {
    "unit_id": "d896c4e121265ba6ff52b101783e640674de0307743802ab2f8eb406cfcb3fe7",
    "sha256": "55cf7973fa7b3bf7b06468609dd08dba8e249aef3fbf0cfdd2a04f2084ea63f9"
  },
  {
    "unit_id": "500c1c04d3e2272cd217c2c1d470bc6413f47ba9c987e0d95cda371bae0a2b38",
    "sha256": "4ffafb2daae9a2b9309fe8469d93f5a7571614314be39fcd2ed193059857529c"
  },
  {
    "unit_id": "08798a36cacf4d87b574110cdc6a6b27ded19f0a20ae090423eafc4aebb34f9c",
    "sha256": "15263cd5822b343a180897154aebfd6a35e946be770a12b63d9f2f7dc7d2b0e5"
  },
  {
    "unit_id": "fbf1c8f24c328cc5f1dcdc1064d6b2c69f46873ad4114c39dcecbc63f171acd8",
    "sha256": "1f56712022ae362d17d3920b9a01562908761b71b8e929982a4d38e3b1f34c94"
  },
  {
    "unit_id": "bd1b0be31c3d35087c9650de2aff877e7543eed84705c86f720eba7ba31145d7",
    "sha256": "3d424c70f77dd494627dccf6f776fe8e13c03f4433cd8550bf7c69fdebf9235f"
  },
  {
    "unit_id": "0b7f0f2af9895cf58d0864dbe737d426d88a8d26563e602248545718a0d7149f",
    "sha256": "4837b7468b6fa4cdbcf2d2e81cd6aa5d5d6ddb5bfd338eb023f83010c7ec9813"
  },
  {
    "unit_id": "5acf6dfca3a301526c44fd4202be091078e9245830c74f19b30bbb2efa7fb628",
    "sha256": "d3fe0eb5e1b43d9cea851844793f9b616b956204651ae1d23d59214b3ce4741e"
  },
  {
    "unit_id": "f92d5a5fb722855cd03acbf040514d9b0ac061ed5eaffd4db70d1f7cd8713067",
    "sha256": "18e677ed11c731c3af98c2719adff9c4beae4e0a54cc1ea4ef466b3485d48d0e"
  },
  {
    "unit_id": "8399f9ab6467f1402bb637e8b1edb1a96ba37a8a34fe3d9041a767acd1fbe879",
    "sha256": "ea27e471b77694b392cd549efe8ad0fdc51a91e3d74919093da3c69a130f7f74"
  },
  {
    "unit_id": "9f26825277a96eb918ddc3af54ef379d346176b0e8962de6887404d3d4f69e9c",
    "sha256": "251b5edda4c64f14127505eb7463d6c2c41f727920dcb9363001ad4a03868573"
  },
  {
    "unit_id": "98aa58af3f84dfb45abf4b68aa75defe86b79e6b92b91775d7eec7ad77b5d2b4",
    "sha256": "1ce7d584f2aa2189a7bd15379db9d1a23e318bce17119dd09b3862a9d469535f"
  },
  {
    "unit_id": "53e2dfb94ef97ab32634271323ab82ec3ed7f1e3f35105b630f6b321ba0d7eb2",
    "sha256": "97c4648f66fc4a7a27d45aa7dba4aa704977b5229c5f724844d458859dfdfdca"
  },
  {
    "unit_id": "8cbf369fd1da4a662be098879bd04526ab6c1f5a4c3d985d16b00089579dd50b",
    "sha256": "6f2c7e3008cea58bc5baee2d8f44f7504f992d523fb2ebebc00f9f1934cc76d0"
  },
  {
    "unit_id": "4722ce165694caf60621a4e71faf39b91b50d224ae6a709ecf7a51f288bb046a",
    "sha256": "a7e5be5c85ed6829f6ba7294eddc3c61a005bcb64ffbed13f228a5893d2a9c3d"
  },
  {
    "unit_id": "36c7e33c819a283c63643dba93c9c7c4baa33698065722709e040c36c28d1189",
    "sha256": "a4b28b035c9b93b8ea66c90adef5634b93b4b52ec21c02514b836ffa92ff9f5d"
  },
  {
    "unit_id": "141c119bb70320be8d9fe2230d8567f77c6af8f371498ea0c709a3d8e31a2d40",
    "sha256": "8fef23bae6a391edc44e92c2299f72679a34f48ad79186c2ee27404f5081ca1c"
  },
  {
    "unit_id": "486daebd77106ba1fb86c3a8ac654d548500f983434c27b8a10010e95129d847",
    "sha256": "744e500803436d5aa917c4542a697c57b8710e0406363ce62c3e6c5ee5fb45a6"
  },
  {
    "unit_id": "4b355e1d665ecdba11a72ee9dfb146ef0a066bc0fcdb0f78c36744099e799488",
    "sha256": "0c25643e3e09012737771c843f99024110cd743e079c3912e2a4064d8db655be"
  },
  {
    "unit_id": "24a5c34c4c8182700b71b1da762987c3fce187575188ba336987be97d58ec15f",
    "sha256": "0b872dc2b1ce80792eff9f0aef793487280a0c4ba285b5f14433f444b324c7d9"
  },
  {
    "unit_id": "cf9d7d3a9912e358a4d262ff5a977887b532679b0821fb111cb6c942fdf64c0d",
    "sha256": "088bb3f68ef19133aa594eb754b5609659fb18d59baba29307e128615ec0d466"
  },
  {
    "unit_id": "2681c7373e991a25eb4f1e12631eb3c2ab03be7d3e9d0e013f41015af12a0537",
    "sha256": "98aa3fbe401dcc84f07f710407471f856ad76739f199de025018f508ea35a154"
  },
  {
    "unit_id": "937518288bb6865fd3d3404eff912f8fbc29a8ad836c838eea293fcce5c5a3a7",
    "sha256": "fd0bf0d3d4ec42679ceb58c2036746dc4f67de5049bc7a9a5b439da275502c7e"
  },
  {
    "unit_id": "2b1f42fc2ff0a9cd858b5248f7f0eb3e78dd7ef01a25f126205141ee9e9351bc",
    "sha256": "34bd6c2d1319d34ec07d810a82120fdb4b420fdd81018500a6f05156a6d99461"
  },
  {
    "unit_id": "19253686d00e41b6ec5e7ed13202c4e95e222bfc416ed584a718f93e3d31c8ae",
    "sha256": "c8664f4c9c1358729b0874519f602c4bda1d6c17557009827f22919e6ccc4f84"
  },
  {
    "unit_id": "a94243f165f931afb783f5117b969a9e8a805281625d2898c1e2deb6bc3f823f",
    "sha256": "193b2d7607369a5b238579aab5ae525c34cbce120c69d9f181e3f7a598bc8236"
  },
  {
    "unit_id": "682e1cf581affd4812741088e28c27e09d4b13b945213b6ce8367b7d796ca8d0",
    "sha256": "c086b2525df95613ef4c05fbea25e4963cf2da846a9238b66bbbfc605bf28ffc"
  },
  {
    "unit_id": "dc773d462ae2ddd5704acaea68e988af7e6588f87aa369bdb75ffce0a0eccf5c",
    "sha256": "238ad1c0a05bc1476f96b55f6e6c4a611e295c78024bb55e4cc12c854b3467de"
  },
  {
    "unit_id": "2d4118fb4f826c90657c29f9ad8e4b31e2aee7c1f00d4b41fd825cbab60e7245",
    "sha256": "41f77d27d4201b7694ed32b7f2def351a42eaabd040150ed1377c58eb9ea8c00"
  },
  {
    "unit_id": "e066ea1bf4ccb08ccda32a307e88a08e78fc094e1aa92d05e08686d6c8e3cfc2",
    "sha256": "77096066ec67ed9da4fd2b132bcbf43c7e367d143c73629a2bc65a6eee22e538"
  },
  {
    "unit_id": "f3aeb79f3fa55462351494e45ce9477d9b52423badefe550d995538ed5e355cd",
    "sha256": "d612547e97ad0cbe30782a6c2f121949f1016bf52524e53856795b8472f0d46c"
  },
  {
    "unit_id": "36d3c8a97ea7a00d06ea2505cb5f48678c08f97d40b8702e28226941dbc48250",
    "sha256": "9fcf12dde586a016a075afba7b764794b56c665867fcca5e91c5815d91651796"
  },
  {
    "unit_id": "8345eb57440c7d4045718cf15f5709e79a4309d809bbbe62022252b3f5e1bb25",
    "sha256": "f256341621dc676980825c5fcad3c7d20b3cc596664ed2167a119bf87cb360e9"
  },
  {
    "unit_id": "41b9e27c02510c61758a9466abc909c661e8ba0f281b17fd5c969f87e0209631",
    "sha256": "c776979eb03ee92586126a06442bf44fffdfda3724ba1876a2e8323807040d01"
  },
  {
    "unit_id": "b2192db14b31db50e3895592cb8e8962ec223a487b5b475d8822a36d18904166",
    "sha256": "af1608960b3f28b7ceda5fe2d4164e23ae24bb665405443591d8513701517ae2"
  },
  {
    "unit_id": "3a3440ae457ab39ddcdafe06ab3ea7c7fff0cc666319af0a8dc165e970dd14fc",
    "sha256": "094c361a489cdfaf085d19aec653ee8ff80d30f8d6211b9767583570171602e4"
  },
  {
    "unit_id": "078c500b59539c260ff52c519db52dfd227713a70f8c2957aff486015a03b082",
    "sha256": "fdc80c18aac00b0a1bdc257f3916e5bf43d9655c7cf9af6402f33d4f558818a3"
  },
  {
    "unit_id": "1d8281275ac0906d1abd537f364990626066711ae6d228e662860898851e2aa3",
    "sha256": "a19691ca3ca610ede2ef5d08b60d73898d5bb1677dd3d68aa94834107439bcfe"
  },
  {
    "unit_id": "8794033ee01f4172f65fecb699311314ecd881d6e9f459d84085ebda7dad13ee",
    "sha256": "94dc3bff288063bdf1f773c3b606d0d3fcdf4029406bcad0259924d766d8bfda"
  },
  {
    "unit_id": "ee7811855e7833ca6d4be9f7198c9bbf9b8e6c9c4f69bfe9d179a04e6e369a89",
    "sha256": "2457dc639e12dbb246f0d364ae0f6da1d767341d3d6276d78445de22070c1689"
  },
  {
    "unit_id": "78fa9fb6de6757661b556a3cf349aca1eeae04eb809bdd08aa4fe71a931434cd",
    "sha256": "28d8028f71ee1a02779f638ee72b0b545bb34f34c44e67c628eac11d3e4e3f15"
  },
  {
    "unit_id": "106fde3b8e1c4ce02e789079169f4418d7259289f65107b7c09078aab6f10362",
    "sha256": "7674a10bad0e60ab5100a77c232e0cf551f4b4e2aabd46ca477a9a4d1d915dd5"
  },
  {
    "unit_id": "1d40226900f9aa1c476697ace430b56aca9a929d8adb8441deb6d15236ddb0d0",
    "sha256": "91994c84048c6f7a1358779001f28d13db7b7513725295b8b1c0436d8f10071b"
  },
  {
    "unit_id": "58cad4738382f81b9bf12dd212d32b469d3f9bcc8c641cd1a37be34400b58189",
    "sha256": "8f804f21074db7ce40962db40ab674f50674b6b4f14a7cd835c123aafb2bb0c3"
  },
  {
    "unit_id": "cecf5963bfa4c63015edc997fc41cbb630260ad00283aefd092401ed48980b79",
    "sha256": "bca2fd0a5bf6648753b8e5151c2c3043ee75d996d38800ff9a7414e0e99913c1"
  },
  {
    "unit_id": "89053e66dd6229076e311d63199d1eb355c04a36cd528c44c2f2dcdb6e23b022",
    "sha256": "bf8fcdede9b3c3ca65a2113a2b7ea12702d71bb36f3f4f604bb417bd0a412fc8"
  },
  {
    "unit_id": "1a099eaf1c81b126a32604c5d67ef6743c43afb62c88701754b8052d234dc990",
    "sha256": "284d9d1d33e53792df2c06f9623969805a2f369808e6e5dc52781178951291e7"
  },
  {
    "unit_id": "8682ba1262a0de221d43e6f68184738906b81eed093b111312ca0f4c932067fc",
    "sha256": "925f4708c3dd06166cbca603872b5fab56bd30750b94f63dcb22cd90f47d8a42"
  },
  {
    "unit_id": "4fdece23f36a84b5294e6a8445073057d64e633c8b459aab167270f23cc44c95",
    "sha256": "ea49acb46529e52890dc2349de0e4413704be5e913d8c554232ea52b55c1ccd5"
  },
  {
    "unit_id": "8939714eb84fc793f3d7945de71c55c8528f04352c93b2d0cef7042b97732657",
    "sha256": "e51a6392129cebb31fc78a2d970796dfc3f78241b1e028f0cc4f6ffc971a54bd"
  },
  {
    "unit_id": "5bca8125eee5bce61f32bd73443cd3674d0323811ea7e61302edc285599f758a",
    "sha256": "0dce52cbb53dd9454e2c5b5c85081b2b9fbd1f5f2bc2cc250f8a523cc5c44f14"
  },
  {
    "unit_id": "e1f4bedaecabd872d98bc2056087ca4c674f06f9a2185b576ef23b1460aebb99",
    "sha256": "411ff43819ff2d889e2baa8a9df1f9ee507847f91f65fef9c771822f9936aba3"
  },
  {
    "unit_id": "a53b390914ce8a0e5a3608483338a3b6cf3892a162487003e70fb44cc42abe53",
    "sha256": "8d1ed6bc2dc5fcd7241636689084e70c67549e34ce16fed54b7c9effd25d133d"
  },
  {
    "unit_id": "28253ea210016f36301a4cb0ce883e29dda5225e3f2c394c5059ec3d9d9d0d71",
    "sha256": "fe0d41ea0dcabc3972773b9923378f035ea205a2af59454f67958cf1dac8e96a"
  },
  {
    "unit_id": "a56000f1b5ba30242ee6d3299e6d180b1e53ee86a8c049d3790a0768e1c34f45",
    "sha256": "0231451041d71c0bc776fed42db52e847b240121933f85354e80410882b06903"
  },
  {
    "unit_id": "f299d9d527320530e27f79f29a40d543d1bcb329e8044582693031b21cfc2087",
    "sha256": "75cd7a72a72eab41f7097212c07ba7215451efd5f2fabf0bd2e2a1eadeae97ef"
  },
  {
    "unit_id": "45a203ad0c4186979780cb604c01363aad28f5ccaaccddb826dbe1ebb23c13ee",
    "sha256": "38efdac2ccb14e8b58f2180bce5c5a488c597efa74e6a568dd3d582fa9cf619b"
  },
  {
    "unit_id": "08d5327c1ba0ba9e2620280f2247bf8c85e893fff4304040d26372fe80e6190a",
    "sha256": "367e1fdc8a666b3cc22e38c17db5a677cf5f6c13a4a3ebdcd72e541a347a1638"
  },
  {
    "unit_id": "b240e1916234bc9238c3d2e2e09aadd04772d378da3ac6cb194e2962dc5e52d1",
    "sha256": "2e0198fb3291ffc5a76c775a67d345e7905a64c35cf3b2f365b7ee144f37391c"
  },
  {
    "unit_id": "b2c9b997a8371c43ced7a8ed0a8916b1c32fa4e190e457194a539dada4f7d1ef",
    "sha256": "76837a25c98e72b3ae4fd97bb8753e6523126ddd2351069177691203b7379503"
  },
  {
    "unit_id": "a35ebd95a096badfbb1cd039b7fe99c1ed53ac7bca7aa272bb8dd7bc8c9ed2c0",
    "sha256": "291d120f3e32bcc7744d5fe01cde48bbe6ac5a5bd95afcacf4150bf6d39ac598"
  },
  {
    "unit_id": "b25b11faf6fcde3b89cba9bbdca596d9ee0527558fb7a1ced96d7723f5e9a1ac",
    "sha256": "1400261879e0d792bf2b64a62d650e81b0544f6c8e509613c6f004ec30f75b96"
  },
  {
    "unit_id": "2818c7f81f399e1556261fd526584c312adfad06aaca751222f523a638c87675",
    "sha256": "9f6a7cba7126f1f7ae9bfb0b807a7a3525e6ead54a23d57fb939242267dc2193"
  },
  {
    "unit_id": "f090d710eb1b445086b31777e69f8c1ae2b3a9337afd8a7f88c367c5530ace0e",
    "sha256": "14190f42551a67b0f48898cca261d32ea3129ef0de6c1ceb60a8518c78cab1cd"
  },
  {
    "unit_id": "2da763c85be82a6f1e290b5052b782a009185f049be8e3df52c13b854a771d56",
    "sha256": "eab87ec2c50cc0a8e2d46b73bbbc20b9355297b36cbb39a0e8e17dac117f7c5f"
  },
  {
    "unit_id": "837534c842f33d8fd86698f22b26cbad0b2fe3b83cc7a5e7dc61899913af4996",
    "sha256": "9bf9a874a48411436040538eba0ea4aa93b5d6d33ad69cfc0523510fc4daeceb"
  },
  {
    "unit_id": "c713a660efa94c72e263b213170b853f88ac0f193d49343571f7053fe30dfdc4",
    "sha256": "cc54d4ca26441482d1c862b339ccabd8663ab12cb2188f16200f857ac66eedf6"
  },
  {
    "unit_id": "c46638a7904b3524f64e86596585f6d988201797cc3f2ed56ba6acdb066136d5",
    "sha256": "5432df4e2372ec3553494d24364a22bb3225498e458521e7f028cde72237b40f"
  },
  {
    "unit_id": "44261eb4d622b7ab54254fb29b329a9580f00058379c92574025684990976166",
    "sha256": "0b285de9062c8bcd09e10273295d30f036d9e2d0d85f5db2e67b8fadf16e5d0d"
  },
  {
    "unit_id": "9857472f615bf6117aab4b29775676b498e9d9f8c3a7697f0a22b4f3c4944e96",
    "sha256": "035cb4fabac9d04dbbb00405fdbfae918b82772378759f4cd4d57ea3503a1d62"
  },
  {
    "unit_id": "74a93509fcabdf00104248a19cb510c43c9a3378b17926f16112b81d601bb440",
    "sha256": "af45a3b76dafd7aa2011af1596210adc5dffb952161c37ca68440098375050dd"
  },
  {
    "unit_id": "3ce3b206980e8746be54e767e76679518cc24687c74f1619282504950aee7f11",
    "sha256": "352de1d9cf61dbf2fcd74788931d6220bbd3417c97a6b4e9f5e63cd90f6181e9"
  },
  {
    "unit_id": "e858d0dd6e787fea463090be1565cf4c4a566417d34bc119d70b82682d7d2ad0",
    "sha256": "1b410d11172e129770707f88833a96dd9b33080ae48a0692925caee36c14ddaf"
  },
  {
    "unit_id": "6766f192637f280a5d61b0c51f09af799c4205d1093be0f5a56fb75ba51d220d",
    "sha256": "d1ee4068901360dc5ad18886f57c99b3d7895f5b30d7e7a8c2080e8c05c7e7ae"
  },
  {
    "unit_id": "29618aed05aa4728b1cf27428b962ea96d34eb9caff5034db9f8a36bcf788685",
    "sha256": "e807eebe1f27d44e3acb4350c12165ca35a73b8b47eca0785589bb0de35b02ca"
  },
  {
    "unit_id": "6a84f3c6889cde1899f514406149f20df8f3f5d4bf5f368e5d058b22a51202e9",
    "sha256": "6dc1f85ddce5bb1e811126bc5f7eda7e865ac0e8137da05e88d20d3288c46aad"
  },
  {
    "unit_id": "74979975bececbff2596f2946afe377535f4914c622a351197e0d8894c0fe193",
    "sha256": "2438995239e70b2e6916a8ee8a5350294a03c02c6540b6e972467c15026a20f0"
  },
  {
    "unit_id": "c49fba5d98ea7bea6b97302bb1d5aadee4e5220ef88d9d1b141e2e7d493bd781",
    "sha256": "c3c4a895ca683e1dfca93bc22c42c95a2d5de0a5c944571eb458889ada505227"
  },
  {
    "unit_id": "79ca60eae2a83f0ac64b0af10009d570f2f512578ecbb866c9c75d94eb683005",
    "sha256": "790e5d2c75e6aa1437826955f2e94d14b6ee76548ad40e1bb02c244f212107b5"
  }
]








def check(evidence,lean_root,claim='P10'):
    if claim not in ('P10','B08','B10'):raise ValueError('unknown census mathematical claim')
    config=evidence.config(claim);manifests={}
    for key,digest in MANIFESTS.items():
        data=evidence.path(config[key]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('P10 manifest commitment differs: '+key)
        manifests[key]=json.loads(data)
    original,completed=manifests['original'],manifests['completed']
    if len(original)!=120 or len(completed)!=120 or [r['unit_id'] for r in original]!=[x['unit_id'] for x in CONTEXTS] or [r['unit_id'] for r in completed]!=[r['unit_id'] for r in original]:
        raise ValueError('P10 ordered census inventory differs')
    if not all(r['overall_registered_claim_status']=='PASS' for r in completed):raise ValueError('P10 completion statuses differ')
    records=[]
    for row,commitment in zip(original,CONTEXTS):
        data=evidence.path(config['contexts']+'/'+row['unit_id']+'/CONTEXT.json').read_bytes()
        if hashlib.sha256(data).hexdigest()!=commitment['sha256']:raise ValueError('P10 context commitment differs: '+row['unit_id'])
        context=json.loads(data)
        if context['identity']['unit_id']!=row['unit_id']:raise ValueError('P10 context identity differs')
        record=extract(context,row['certificates']['strictness'])
        if claim=='B10':
            expected=[]
            for f,q in zip(FIELDS,record['labels']):
                for a in sorted(set(q)):
                    block=[i for i,v in enumerate(q) if v==a]
                    v=sum(record['z'][i] for i in block);u=sum(record['z'][i]**2 for i in block)
                    det=Q(len(block)*u-v*v,record['D']**2)
                    expected.append({'context':f,'atom':a,'Gram_det_exact':str(det),'positive':det>0})
            supplied=completed[len(records)]['atoms']
            if supplied!=expected:raise ValueError('B10 retained atom determinant table differs')
        records.append(record)
    if claim=='B10':
        expected_atoms=atom_selectors(records)
        actual_atoms=(Path(lean_root)/'BornCalculus/CensusAtomInputs.lean').read_text()
        if actual_atoms!=expected_atoms:raise ValueError('B10 coordinate witness embedding differs')
    expected=render(records);actual=(Path(lean_root)/'BornCalculus/CensusInputs.lean').read_text()
    if actual!=expected:raise ValueError('P10 integer frame/label/witness embedding differs')
    return {'status':'PASS','contexts':120,'point_pairs':120,'readout':'raw atom 0','manifest_sha256':MANIFESTS,
            'context_commitments':len(CONTEXTS),'embedding_sha256':hashlib.sha256(actual.encode()).hexdigest(),
            'boundary':'external byte/extraction/full-record binding, not a Lean provenance theorem',
            **({'atom_selector_sha256':hashlib.sha256(actual_atoms.encode()).hexdigest(),'active_atoms':1006,'singular_atoms':27,'singular_contexts':20} if claim=='B10' else {})}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--claim',choices=('P10','B08','B10'),default='P10')
    parser.add_argument('--lean-root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    from born_ladder.claims import Evidence
    try:print(json.dumps(check(Evidence(args.data),args.lean_root,args.claim),sort_keys=True))
    except (ValueError,OSError,KeyError) as exc:parser.exit(1,f'FAIL: {exc}\n')

if __name__=='__main__':main()
