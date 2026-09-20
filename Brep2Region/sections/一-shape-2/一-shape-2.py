#
#           DFC Script
# =============================
#   Description: 一-shape-2 - L形折线基准
#          Date: 2026-08-19
#       Version: 1.0
#
    S_1 = theModel.createSect( sectionName = "一-shape-2");
    S_1_SP_1 = theModel.createSecNode( x = 0.000, y = 0.000, z = 0.000, theSect = S_1);
    S_1_SP_2 = theModel.createSecNode( x = 0.000, y = 43.950, z = -1.130, theSect = S_1);
    S_1_SP_3 = theModel.createSecNode( x = 0.000, y = 47.810, z = -7.550, theSect = S_1);
    S_1_SL_1 = theModel.createSecCurve( start = S_1_SP_1, end = S_1_SP_2, theSect = S_1);
    S_1_SL_2 = theModel.createSecCurve( start = S_1_SP_2, end = S_1_SP_3, theSect = S_1);
    theModel.drawModel();
