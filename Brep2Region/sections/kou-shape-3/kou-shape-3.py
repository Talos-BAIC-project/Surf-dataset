#
#           DFC Script
# =============================
#   Description: Generated from DFCModel
#          Date: 2026-07-29
#       Version: 4.4.34
#
    S_3 = theModel.createSect( sectionName = "S_1");
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 0.00, z = 0.00, theSect = S_3);
    S_3_SP_1 = theModel.createSecNode( x = 0.00, y = 1.50, z = 51.00, theSect = S_3);
    S_3_SP_2 = theModel.createSecNode( x = 0.00, y = 43.50, z = 51.00, theSect = S_3);
    S_3_SP_3 = theModel.createSecNode( x = 0.00, y = 43.50, z = -51.00, theSect = S_3);
    S_3_SP_4 = theModel.createSecNode( x = 0.00, y = 1.50, z = -51.00, theSect = S_3);
    S_3_SL_1 = theModel.createSecCurve( start = S_3_SP_1, end = S_3_SP_2, theSect = S_3);
    S_3_SL_2 = theModel.createSecCurve( start = S_3_SP_2, end = S_3_SP_3, theSect = S_3);
    S_3_SL_3 = theModel.createSecCurve( start = S_3_SP_3, end = S_3_SP_4, theSect = S_3);
    S_3_SL_4 = theModel.createSecCurve( start = S_3_SP_4, end = S_3_SP_1, theSect = S_3);
    theModel.drawModel();
