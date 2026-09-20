#
#           DFC Script
# =============================
#   Description: 一-shape-1 - 纯水平线基准
#          Date: 2026-08-19
#       Version: 1.0
#
    S_1 = theModel.createSect( sectionName = "一-shape-1");
    S_1_SP_1 = theModel.createSecNode( x = 0.000, y = 10.800, z = 4.290, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = 0.000, y = 81.220, z = 4.290, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    theModel.drawModel();
